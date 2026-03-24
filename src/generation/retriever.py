from __future__ import annotations

import json
import importlib
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import yaml

try:
    import faiss
except Exception:  # pragma: no cover
    faiss = None

class NarrativeRetriever:
    def __init__(self, corpus_path: str = "data/raw_corpus", index_path: str = "data/vector_index"):
        self.corpus_path = Path(corpus_path)
        self.index_path = Path(index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)

        with open("config/model_config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        self.embedding_model_name = cfg.get("local", {}).get(
            "embedding_model",
            "sentence-transformers/all-MiniLM-L6-v2",
        )

        self.encoder = None
        try:
            st_module = importlib.import_module("sentence_transformers")
            SentenceTransformer = getattr(st_module, "SentenceTransformer")
            try:
                self.encoder = SentenceTransformer(self.embedding_model_name, local_files_only=True)
            except TypeError:
                # 兼容旧版本参数签名
                self.encoder = SentenceTransformer(self.embedding_model_name)
            except Exception:
                self.encoder = None
        except Exception:
            self.encoder = None

        self.documents: List[Dict] = self._load_corpus()
        self.index, self.doc_vectors = self._load_or_build_index(self.documents)

    def _load_corpus(self) -> List[Dict]:
        files: List[Path] = []
        if self.corpus_path.is_file():
            files = [self.corpus_path]
        elif self.corpus_path.exists():
            files = sorted(self.corpus_path.glob("*.jsonl"))

        docs: List[Dict] = []
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    row.setdefault("id", f"doc_{len(docs):04d}")
                    docs.append(row)
        return docs

    @staticmethod
    def _hash_embed(texts: List[str], dim: int = 256) -> np.ndarray:
        vectors = np.zeros((len(texts), dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in text.split():
                h = hash(token) % dim
                vectors[i, h] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-8
        return vectors / norms

    def _embed(self, texts: List[str]) -> np.ndarray:
        if self.encoder is not None:
            vectors = self.encoder.encode(texts, show_progress_bar=False, convert_to_numpy=True)
            vectors = vectors.astype(np.float32)
            norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-8
            return vectors / norms
        return self._hash_embed(texts)

    def _load_or_build_index(self, docs: List[Dict]) -> Tuple[object, np.ndarray]:
        if not docs:
            return None, np.zeros((0, 1), dtype=np.float32)

        corpus_texts = [
            f"{d.get('setting', '')} {d.get('location', '')} {d.get('plot_summary', '')} {d.get('text_segment', '')}"
            for d in docs
        ]
        vectors = self._embed(corpus_texts)

        if faiss is None:
            return None, vectors

        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)

        faiss.write_index(index, str(self.index_path / "narrative.index"))
        np.save(self.index_path / "narrative_vectors.npy", vectors)
        with open(self.index_path / "narrative_meta.json", "w", encoding="utf-8") as f:
            json.dump({"count": len(docs), "dim": int(dim)}, f, ensure_ascii=False, indent=2)

        return index, vectors

    def retrieve(self, query: str, current_location: str, k: int = 3) -> List[Dict]:
        if not self.documents:
            return []

        qv = self._embed([query])

        if self.index is not None and faiss is not None:
            scores, idxs = self.index.search(qv, min(k * 4, len(self.documents)))
            cand = [(int(i), float(s)) for i, s in zip(idxs[0], scores[0]) if i >= 0]
        else:
            sim = np.dot(self.doc_vectors, qv[0])
            idxs = np.argsort(-sim)[: min(k * 4, len(self.documents))]
            cand = [(int(i), float(sim[i])) for i in idxs]

        ranked: List[Tuple[int, float]] = []
        for i, s in cand:
            loc_boost = 0.08 if self.documents[i].get("location") == current_location else 0.0
            ranked.append((i, s + loc_boost))

        ranked.sort(key=lambda x: x[1], reverse=True)

        out: List[Dict] = []
        for i, score in ranked[:k]:
            d = self.documents[i]
            out.append(
                {
                    "id": d.get("id", f"doc_{i:04d}"),
                    "location": d.get("location"),
                    "scenario": d.get("text_segment", ""),
                    "plot_summary": d.get("plot_summary", ""),
                    "similarity": round(float(score), 4),
                }
            )
        return out
