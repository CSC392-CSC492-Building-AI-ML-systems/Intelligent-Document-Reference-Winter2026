"""Flask application for document search API."""

from flask import Flask, jsonify, request
from search_engine import SearchEngine

app = Flask(__name__)
engine = SearchEngine()


@app.route("/api/search", methods=["POST"])
def search():
    query = request.json.get("query", "")
    top_k = request.json.get("top_k", 5)
    results = engine.search(query, top_k=top_k)
    return jsonify({"results": results, "count": len(results)})


@app.route("/api/index", methods=["POST"])
def index_document():
    doc = request.json.get("document", "")
    metadata = request.json.get("metadata", {})
    doc_id = engine.index(doc, metadata)
    return jsonify({"id": doc_id, "status": "indexed"})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "indexed_docs": engine.count()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
