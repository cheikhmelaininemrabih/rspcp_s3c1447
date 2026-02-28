import sys
import os
import time
import subprocess
import random
from ortools.sat.python import cp_model

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.parser import RCPSPInstance
from src.gans import GANS

def solve_with_gans(instance_path, seed, generations=500):
    """Run GANS with a specific seed to get a hint quickly."""
    print(f"--- Running Fast GANS Seed {seed} ---")
    random.seed(seed)
    
    optimizer = GANS(instance_path)
    # Lighter parameters for faster seeding
    optimizer.params['pop_size'] = 150
    optimizer.params['generations'] = generations
    optimizer.params['ns_frequency'] = 50 # Much less frequent NS
    
    best_schedule, best_makespan = optimizer.run()
    return best_schedule, best_makespan

def solve_full_cp_ultra(instance_path, time_limit=3600, hint_pool=[]):
    instance = RCPSPInstance(instance_path)
    model = cp_model.CpModel()
    
    # Use sum of durations as upper bound for variables
    horizon = sum(instance.durations)
    
    starts = {}
    ends = {}
    intervals = {}
    demands = [[] for _ in range(instance.num_resources)]
    
    for job in range(1, instance.num_jobs + 1):
        dur = instance.durations[job]
        start_var = model.NewIntVar(0, horizon, f'start_{job}')
        end_var = model.NewIntVar(0, horizon, f'end_{job}')
        interval_var = model.NewIntervalVar(start_var, dur, end_var, f'interval_{job}')
        
        starts[job] = start_var
        ends[job] = end_var
        intervals[job] = interval_var
        
        reqs = instance.requests[job]
        for r in range(instance.num_resources):
            if reqs[r] > 0:
                demands[r].append((interval_var, reqs[r]))

    # Precedence Constraints
    for i in range(1, instance.num_jobs + 1):
        if i in instance.successors:
            for succ in instance.successors[i]:
                model.Add(starts[succ] >= ends[i])
                
    # Resource Constraints
    for r in range(instance.num_resources):
        cap = instance.capacities[r]
        if demands[r]:
            intervals_r = [d[0] for d in demands[r]]
            reqs_r = [d[1] for d in demands[r]]
            model.AddCumulative(intervals_r, reqs_r, cap)
            
    # Add multiple hints from the pool
    for hint in hint_pool:
         for job, start_val in hint.items():
             model.AddHint(starts[job], start_val)
            
    # Objective: Minimize makespan
    makespan = ends[instance.num_jobs]
    model.Minimize(makespan)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 16 
    solver.parameters.cp_model_presolve = True
    solver.parameters.linearization_level = 2
    
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        best_ms = solver.Value(makespan)
        best_sched = {job: solver.Value(starts[job]) for job in range(1, instance.num_jobs + 1)}
        return best_sched, best_ms
    
    return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/ultra_solver.py <instance_path>")
        return
        
    instance_path = sys.argv[1]
    
    print(f"Starting ULTRA SOLVER for {instance_path} - Target: < 154")
    
    hint_pool = []
    best_gans_ms = float('inf')
    
    # Run 2 seeds for diversity but keep it fast
    # We want to spend maybe 10-15 mins on GA and 45-50 mins on CP-SAT
    for i in range(2):
        seed = 42 + i * 777
        sched, ms = solve_with_gans(instance_path, seed, generations=1000)
        hint_pool.append(sched)
        if ms < best_gans_ms:
            best_gans_ms = ms
            
    print(f"\nBest seeding makespan: {best_gans_ms}")
    
    print("\nStarting Ultra CP-SAT Phase (3600s)...")
    start_time = time.time()
    best_sched, best_ms = solve_full_cp_ultra(instance_path, time_limit=3600, hint_pool=hint_pool)
    end_time = time.time()
    
    if best_ms:
        print(f"\nSUCCESS! Final Ultra Makespan: {best_ms}")
        print(f"Total Time: {end_time - start_time:.2f}s")
        
        output_file = "ultra_solution.txt"
        with open(output_file, 'w') as f:
            f.write(f"Instance: {instance_path}\n")
            f.write(f"Makespan: {best_ms}\n")
            f.write("Schedule:\n")
            for job in sorted(best_sched.keys()):
                f.write(f"{job} {best_sched[job]}\n")
        print(f"Solution written to {output_file}")
        
        if best_ms < 154:
            print("RECORD BROKEN!")
    else:
        print("No solution found.")

if __name__ == "__main__":
    main()
