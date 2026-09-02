# run_eval.py
from eval_metrics import faithfulness_score, answer_relevancy_score
from pipeline_semantic import run_semantic

golden_dataset = [
    "What is prompt injection and how do you prevent it?",
    "What are the core functions of the AI RMF?",
    "What is LLM01?",
    "What does GDPR say about AI risk management?",
    "What's the best programming language for beginners?",
]

def run_eval(pipeline_fn, questions):
    results = []
    for q in questions:
        answer, chunks = pipeline_fn(q)
        context = "\n\n".join(chunks)
        f_score, _ = faithfulness_score(answer, context)
        r_score = answer_relevancy_score(q, answer)
        results.append({
            "question": q,
            "answer": answer,
            "faithfulness": f_score,
            "relevancy": r_score.score,
            "relevancy_reasoning": r_score.reasoning,
        })
    return results

def summarize(results, label):
    avg_f = sum(r["faithfulness"] for r in results) / len(results)
    avg_r = sum(r["relevancy"] for r in results) / len(results)
    print(f"\n=== {label} ===")
    print(f"Avg faithfulness: {avg_f:.2f} | Avg relevancy: {avg_r:.2f}/5\n")
    for r in results:
        print(f"[{r['faithfulness']:.2f} | {r['relevancy']}/5] {r['question']}")
        print(f"   {r['answer'][:100]}...")
        print(f"   Relevancy reasoning: {r['relevancy_reasoning']}\n")

if __name__ == "__main__":
    results = run_eval(run_semantic, golden_dataset)
    summarize(results, "Plain semantic pipeline")
