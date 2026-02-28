import sys
import os
import time
from ortools.sat.python import cp_model

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.parser import RCPSPInstance

def solve_marathon(instance_path, hint_file, time_limit=3600):
    instance = RCPSPInstance(instance_path)
    model = cp_model.CpModel()
    
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
            
    # Load hint from file
    current_best = float('inf')
    if os.path.exists(hint_file):
        print(f"Loading record-breaking hint from {hint_file}...")
        try:
            with open(hint_file, 'r') as f:
                lines = f.readlines()
                start_parsing = False
                for line in lines:
                    if line.startswith("Makespan:"):
                        current_best = int(line.split(":")[1].strip())
                    if line.startswith("Schedule:"):
                        start_parsing = True
                        continue
                    if start_parsing:
                        parts = line.split()
                        if len(parts) == 2:
                            model.AddHint(starts[int(parts[0])], int(parts[1]))
        except Exception as e:
            print(f"Warning: Could not parse hint file: {e}")

    # Objective: Minimize makespan with Tight Packing
    makespan = ends[instance.num_jobs]
    model.Minimize(makespan * 100000 + sum(starts[j] for j in starts))
    
    # Optional: Constraint to only look for improvements below the record if we're feeling aggressive
    # model.Add(makespan <= 153)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 16 
    solver.parameters.cp_model_presolve = True
    
    # Tune search for large neighborhood search (LNS)
    # CP-SAT automatically uses many workers for LNS, which is good.
    
    print(f"Searching for solution with makespan < {current_best}...")
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        best_ms = solver.Value(makespan)
        best_sched = {job: solver.Value(starts[job]) for job in range(1, instance.num_jobs + 1)}
        return best_sched, best_ms
    
    return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/bypass_solver.py <instance_path> [hint_file]")
        return
        
    instance_path = sys.argv[1]
    hint_file = sys.argv[2] if len(sys.argv) > 2 else "best_gans_solution.txt"
    
    print(f"Starting BYPASS MARATHON for {instance_path}")
    start_time = time.time()
    best_sched, best_ms = solve_marathon(instance_path, hint_file, time_limit=3600)
    end_time = time.time()
    
    if best_ms:
        print(f"\nFINAL MAKESPAN: {best_ms}")
        if best_ms < 154:
            print("NEW WORLD RECORD NOMINEE!")
            
        output_file = "bypass_solution.txt"
        with open(output_file, 'w') as f:
            f.write(f"Instance: {instance_path}\n")
            f.write(f"Makespan: {best_ms}\n")
            f.write("Schedule:\n")
            for job in sorted(best_sched.keys()):
                f.write(f"{job} {best_sched[job]}\n")
        print(f"Result written to {output_file}")
    else:
        print("Bypass attempt failed to find any feasible solution.")

if __name__ == "__main__":
    main()
