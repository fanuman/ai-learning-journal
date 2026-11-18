import statistics

# ---- Part 1: run-to-run noise -------------------------------------------
# Faithfulness for the same 6 questions, same code, run 3 times (the judge is an LLM, so scores move).
runs = {
    "run 1": [1.00, 0.75, 1.00, 1.00, 0.67, 1.00],
    "run 2": [1.00, 1.00, 1.00, 0.80, 0.67, 1.00],
    "run 3": [1.00, 0.75, 1.00, 1.00, 1.00, 1.00],
}
averages = [statistics.mean(scores) for scores in runs.values()]
for name, avg in zip(runs, averages):
    print(f"{name}: average faithfulness {avg:.3f}")
spread = statistics.stdev(averages)
print(f"mean of the runs {statistics.mean(averages):.3f}, standard deviation {spread:.3f}")
print(f"a drop smaller than about 2 x {spread:.3f} = {2 * spread:.3f} could be pure noise")

# ---- Part 2: does the LLM judge agree with a human? ----------------------
# 20 answers, each labelled "faithful" (True) or not by a human and by the judge.
human = [True] * 16 + [False] * 4
judge = [True] * 15 + [False] * 1 + [True] * 2 + [False] * 2
both_yes = sum(h and j for h, j in zip(human, judge))
both_no = sum((not h) and (not j) for h, j in zip(human, judge))
n = len(human)
observed = (both_yes + both_no) / n
human_yes, judge_yes = sum(human) / n, sum(judge) / n
by_chance = human_yes * judge_yes + (1 - human_yes) * (1 - judge_yes)
kappa = (observed - by_chance) / (1 - by_chance)
print(f"\nraw agreement {observed:.2f}, agreement expected by chance {by_chance:.2f}, Cohen's kappa {kappa:.2f}")
