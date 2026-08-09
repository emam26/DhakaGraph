"""Graph Neural Network (GCN) for cell-level urban function classification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import folium
import networkx as nx
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from dhakagraph.config import EXPANDED_DHAKA_STUDY, StudyArea
from dhakagraph.overture import load_or_download_overture, process_overture_roads
from dhakagraph.urban import ATLAS_FEATURE_COLUMNS, build_urban_atlas


def project_root() -> Path:
    """Return repository root path."""
    return Path(__file__).resolve().parents[2]


class GraphConvolution:
    """Spectral Graph Convolutional Layer H^(l+1) = activation(A_hat * H^(l) * W + b)."""

    def __init__(self, in_features: int, out_features: int, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        # Xavier / Glorot initialization
        limit = np.sqrt(6.0 / (in_features + out_features))
        self.W = rng.uniform(-limit, limit, size=(in_features, out_features))
        self.b = np.zeros((1, out_features))
        self.dW = np.zeros_like(self.W)
        self.db = np.zeros_like(self.b)

    def forward(self, X: np.ndarray, A_hat: np.ndarray) -> np.ndarray:
        """Forward pass over normalized adjacency matrix A_hat."""
        self.X = X
        self.A_hat = A_hat
        self.AX = A_hat @ X
        return self.AX @ self.W + self.b

    def backward(self, grad_output: np.ndarray) -> np.ndarray:
        """Backward pass computing gradients for parameters and input."""
        N = grad_output.shape[0]
        self.dW = (self.AX.T @ grad_output) / N
        self.db = np.mean(grad_output, axis=0, keepdims=True)
        grad_AX = grad_output @ self.W.T
        return self.A_hat.T @ grad_AX


class GCNClassifier:
    """2-layer Graph Convolutional Network for spatial node classification."""

    def __init__(
        self,
        in_features: int,
        hidden_dim: int,
        num_classes: int,
        lr: float = 0.02,
        weight_decay: float = 1e-4,
        seed: int = 42,
    ) -> None:
        self.gc1 = GraphConvolution(in_features, hidden_dim, seed=seed)
        self.gc2 = GraphConvolution(hidden_dim, num_classes, seed=seed + 1)
        self.lr = lr
        self.weight_decay = weight_decay

    @staticmethod
    def softmax(Z: np.ndarray) -> np.ndarray:
        exp_Z = np.exp(Z - np.max(Z, axis=1, keepdims=True))
        return exp_Z / np.sum(exp_Z, axis=1, keepdims=True)

    @staticmethod
    def relu(X: np.ndarray) -> np.ndarray:
        return np.maximum(0, X)

    def forward(self, X: np.ndarray, A_hat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Forward pass through 2 GCN layers."""
        self.H1_raw = self.gc1.forward(X, A_hat)
        self.H1 = self.relu(self.H1_raw)
        self.Z = self.gc2.forward(self.H1, A_hat)
        self.probs = self.softmax(self.Z)
        return self.probs, self.H1

    def train_step(
        self,
        X: np.ndarray,
        A_hat: np.ndarray,
        y: np.ndarray,
        train_mask: np.ndarray,
    ) -> float:
        """Execute single gradient descent step over train_mask nodes."""
        probs, _ = self.forward(X, A_hat)
        N_train = np.sum(train_mask)

        # Cross-entropy loss on train nodes
        log_probs = np.log(np.clip(probs, 1e-12, 1.0))
        one_hot = np.zeros_like(probs)
        one_hot[np.arange(len(y)), y] = 1.0

        loss = -np.sum(one_hot[train_mask] * log_probs[train_mask]) / N_train
        loss += 0.5 * self.weight_decay * (np.sum(self.gc1.W**2) + np.sum(self.gc2.W**2))

        # Gradient of loss w.r.t logits Z
        grad_Z = (probs - one_hot) * train_mask[:, None] / N_train
        grad_H1 = self.gc2.backward(grad_Z)

        # ReLU gradient
        grad_H1_raw = grad_H1 * (self.H1_raw > 0)
        self.gc1.backward(grad_H1_raw)

        # Update weights with L2 regularization
        self.gc1.W -= self.lr * (self.gc1.dW + self.weight_decay * self.gc1.W)
        self.gc1.b -= self.lr * self.gc1.db
        self.gc2.W -= self.lr * (self.gc2.dW + self.weight_decay * self.gc2.W)
        self.gc2.b -= self.lr * self.gc2.db

        return float(loss)


def compute_normalized_adjacency(
    graph: nx.Graph, num_nodes: int, node_to_idx: dict[Any, int]
) -> np.ndarray:
    """Compute symmetric normalized adjacency A_hat = D~^(-1/2) * A~ * D~^(-1/2)."""
    A = np.zeros((num_nodes, num_nodes))
    for u, v in graph.edges():
        if u in node_to_idx and v in node_to_idx:
            i, j = node_to_idx[u], node_to_idx[v]
            A[i, j] = 1.0
            A[j, i] = 1.0

    # Add self-loops A~ = A + I
    A_tilde = A + np.eye(num_nodes)
    degrees = np.sum(A_tilde, axis=1)
    inv_sqrt_deg = 1.0 / np.sqrt(degrees)
    D_inv_sqrt = np.diag(inv_sqrt_deg)

    return D_inv_sqrt @ A_tilde @ D_inv_sqrt


def run_gnn_classification(
    area: StudyArea = EXPANDED_DHAKA_STUDY,
    epochs: int = 150,
    hidden_dim: int = 32,
) -> dict[str, Any]:
    """Train GCN classifier on cell spatial feature graph and return metrics."""
    root = project_root()
    raw_dir = root / "data" / "raw"
    layers, _ = load_or_download_overture(area, raw_dir)
    processed_roads, road_nodes, road_edges = process_overture_roads(layers)

    cells, contiguity_edges, summary = build_urban_atlas(
        layers,
        processed_roads,
        road_nodes,
        road_edges,
        area,
    )

    cell_ids = cells["cell_id"].tolist()
    node_to_idx = {cid: idx for idx, cid in enumerate(cell_ids)}

    # Build Graph
    graph = nx.Graph()
    graph.add_nodes_from(cell_ids)
    graph.add_edges_from((str(u), str(v)) for u, v in contiguity_edges.index)

    A_hat = compute_normalized_adjacency(graph, len(cells), node_to_idx)

    # Feature Matrix X
    feature_cols = [c for c in ATLAS_FEATURE_COLUMNS if c in cells]
    X_raw = cells[feature_cols].fillna(0).to_numpy()
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    # Labels y
    y_labels = cells["cluster_id"].to_numpy() - 1  # 0-indexed
    num_classes = len(np.unique(y_labels))

    # Stratified Train/Test split
    train_idx, test_idx = train_test_split(
        np.arange(len(cells)),
        test_size=0.2,
        stratify=y_labels,
        random_state=42,
    )

    train_mask = np.zeros(len(cells), dtype=bool)
    test_mask = np.zeros(len(cells), dtype=bool)
    train_mask[train_idx] = True
    test_mask[test_idx] = True

    model = GCNClassifier(
        in_features=X.shape[1],
        hidden_dim=hidden_dim,
        num_classes=num_classes,
        lr=0.03,
        seed=42,
    )

    loss_history = []
    for _epoch in range(epochs):
        loss = model.train_step(X, A_hat, y_labels, train_mask)
        loss_history.append(loss)

    probs, embeddings = model.forward(X, A_hat)
    preds = np.argmax(probs, axis=1)

    # Evaluation
    test_acc = accuracy_score(y_labels[test_mask], preds[test_mask])
    test_f1 = f1_score(y_labels[test_mask], preds[test_mask], average="macro")
    overall_acc = accuracy_score(y_labels, preds)

    conf_mat = confusion_matrix(y_labels[test_mask], preds[test_mask]).tolist()
    report = classification_report(y_labels[test_mask], preds[test_mask], output_dict=True)

    # Attach predictions & confidence to cells GeoDataFrame
    cells["gnn_pred_cluster"] = preds + 1
    cells["gnn_confidence"] = np.max(probs, axis=1)
    cells["gnn_correct"] = cells["gnn_pred_cluster"] == cells["cluster_id"]

    return {
        "cell_count": len(cells),
        "num_classes": num_classes,
        "feature_count": X.shape[1],
        "test_accuracy": round(float(test_acc), 4),
        "test_macro_f1": round(float(test_f1), 4),
        "overall_accuracy": round(float(overall_acc), 4),
        "confusion_matrix": conf_mat,
        "classification_report": report,
        "loss_history": [round(loss_value, 4) for loss_value in loss_history[::10]],
        "cells_gdf": cells,
        "feature_columns": feature_cols,
    }


def export_gnn_map(
    gnn_results: dict[str, Any],
    area: StudyArea,
    output_html: Path,
    output_report_json: Path,
) -> None:
    """Export interactive Folium map showing GCN predicted urban classes and confidence."""
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_report_json.parent.mkdir(parents=True, exist_ok=True)

    cells = gnn_results["cells_gdf"].to_crs("EPSG:4326")

    report_data = {
        "study_area": area.name,
        "cell_count": gnn_results["cell_count"],
        "num_classes": gnn_results["num_classes"],
        "test_accuracy": gnn_results["test_accuracy"],
        "test_macro_f1": gnn_results["test_macro_f1"],
        "overall_accuracy": gnn_results["overall_accuracy"],
        "confusion_matrix": gnn_results["confusion_matrix"],
        "classification_report": gnn_results["classification_report"],
    }
    output_report_json.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    m = folium.Map(
        location=[area.center_lat, area.center_lon],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    palette = ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2"]

    for cluster in range(1, gnn_results["num_classes"] + 1):
        fg = folium.FeatureGroup(name=f"GNN Predicted Class {cluster}", show=True)
        sub = cells.loc[cells["gnn_pred_cluster"] == cluster]

        for row in sub.itertuples():
            color = palette[(cluster - 1) % len(palette)]
            conf = row.gnn_confidence
            folium.GeoJson(
                row.geometry,
                style_function=lambda x, col=color, c=conf: {
                    "fillColor": col,
                    "color": "#1F2937",
                    "weight": 1,
                    "fillOpacity": 0.3 + 0.5 * c,
                },
                popup=folium.Popup(
                    f"<b>Cell ID:</b> {row.cell_id}<br>"
                    f"<b>True Cluster:</b> {row.cluster_id}<br>"
                    f"<b>GNN Predicted:</b> {row.gnn_pred_cluster}<br>"
                    f"<b>GNN Confidence:</b> {row.gnn_confidence:.2%}<br>"
                    f"<b>Status:</b> {'Correct' if row.gnn_correct else 'Misclassified'}",
                    max_width=260,
                ),
            ).add_to(fg)
        fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))
