def process_results(doc, results):
    out = results[0].strip()
    return {"acc": float("*" in doc["accept"] or out in doc["accept"])}
