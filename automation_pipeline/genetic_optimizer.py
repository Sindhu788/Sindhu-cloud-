"""Genetic Optimization Engine, basic version (Additional Features, B6): an
alternative to the existing grid-search Auto-Optimizer (automation_pipeline.optimizer),
searching the EXACT SAME parameter space (optimizer.tunable_dimensions --
the strategy's own already-configured tunable fields, nothing invented)
via mutation + selection across generations instead of a coordinate-wise
grid sweep. Reuses optimizer._run_in_memory and optimizer._score verbatim
-- the backtest engine itself is never touched, only which parameter
combinations get tried and how they're chosen.

Algorithm (simple, standard GA -- nothing exotic):
  1. Start with a random population of "genomes" (one candidate value per
     tunable dimension), with genome[0] seeded to the strategy's own
     current (baseline) values so the search can never do WORSE than
     doing nothing.
  2. Each generation: score every genome's fitness (the same profit_pct
     scoring grid-search uses), keep the top `elite_count` unchanged,
     breed the rest via single-point-per-gene crossover between two
     fitter parents plus a per-gene mutation chance (swap to a random
     candidate value for that dimension).
  3. Track the best genome seen across ALL generations (not just the
     final one -- a later generation can regress from bad luck in
     crossover/mutation).
"""

import copy
import random

from automation_pipeline.optimizer import tunable_dimensions, _run_in_memory, _score


def _random_genome(dims, rng):
    return {d["id"]: rng.choice(d["candidates"]) for d in dims}


def _apply_genome(config, dims, genome):
    cfg = copy.deepcopy(config)
    for d in dims:
        cfg = d["apply"](cfg, genome[d["id"]])
    return cfg


def run_genetic_optimization(config, exchange, symbol, settings, start_ms, end_ms,
                              population_size=10, generations=5, mutation_rate=0.3,
                              elite_count=2, seed=None):
    dims = tunable_dimensions(config)
    if not dims:
        return {"available": False, "reason": "no tunable numeric/parameter dimensions found for this strategy"}

    rng = random.Random(seed)
    population = [_random_genome(dims, rng) for _ in range(population_size)]
    population[0] = {d["id"]: d["baseline"] for d in dims}  # baseline always in the gene pool

    history = []
    best_genome, best_fitness, best_metrics = None, float("-inf"), None

    for gen in range(generations):
        scored = []
        for genome in population:
            cfg = _apply_genome(config, dims, genome)
            metrics = _run_in_memory(cfg, exchange, symbol, settings, start_ms, end_ms)
            fitness = _score(metrics)
            scored.append((fitness, genome, metrics))
        scored.sort(key=lambda x: x[0], reverse=True)
        history.append({"generation": gen, "best_fitness_this_gen": scored[0][0]})

        if scored[0][0] > best_fitness:
            best_fitness, best_genome, best_metrics = scored[0][0], scored[0][1], scored[0][2]

        elites = [g for _, g, _ in scored[:elite_count]]
        mating_pool = [g for _, g, _ in scored[:max(elite_count, population_size // 2)]]
        new_population = elites[:]
        while len(new_population) < population_size:
            parent_a, parent_b = rng.choice(mating_pool), rng.choice(mating_pool)
            child = {}
            for d in dims:
                child[d["id"]] = parent_a[d["id"]] if rng.random() < 0.5 else parent_b[d["id"]]
                if rng.random() < mutation_rate:
                    child[d["id"]] = rng.choice(d["candidates"])
            new_population.append(child)
        population = new_population

    return {
        "available": True,
        "dimensions_searched": [d["id"] for d in dims],
        "population_size": population_size, "generations": generations,
        "total_candidates_evaluated": population_size * generations,
        "best_genome": best_genome,
        "best_fitness_profit_pct": None if best_fitness == float("-inf") else round(best_fitness, 3),
        "best_metrics": best_metrics,
        "generation_history": history,
    }
