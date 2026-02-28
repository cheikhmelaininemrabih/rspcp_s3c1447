import sys
import os
import time

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ortools.sat.python import cp_model
from src.parser import RCPSPInstance

def solve_full_cp(instance_path, time_limit=600, hint_schedule=None):
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
        
        # Add hint if available
        if hint_schedule and job in hint_schedule:
            model.AddHint(start_var, hint_schedule[job])

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
            
    # Objective: Minimize makespan (end time of the last job)
    makespan = ends[instance.num_jobs]
    model.Minimize(makespan)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 16 # Use more workers if available
    
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        best_ms = solver.Value(makespan)
        best_sched = {job: solver.Value(starts[job]) for job in range(1, instance.num_jobs + 1)}
        return best_sched, best_ms
    
    return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/solve_full_cp.py <instance_path> [hint_file]")
        return
        
    instance_path = sys.argv[1]
    hint_file = sys.argv[2] if len(sys.argv) > 2 else "solution.txt"
    
    hint_schedule = None
    if os.path.exists(hint_file):
        print(f"Loading hint from {hint_file}...")
        try:
            with open(hint_file, 'r') as f:
                lines = f.readlines()
                hint_schedule = {}
                start_parsing = False
                for line in lines:
                    if line.startswith("Schedule:"):
                        start_parsing = True
                        continue
                    if start_parsing:
                        parts = line.split()
                        if len(parts) == 2:
                            hint_schedule[int(parts[0])] = int(parts[1])
        except Exception as e:
            print(f"Warning: Could not parse hint file: {e}")

    print(f"Starting Full CP-SAT solver for {instance_path}...")
    start_time = time.time()
    best_sched, best_ms = solve_full_cp(instance_path, time_limit=300, hint_schedule=hint_schedule)
    end_time = time.time()
    
    if best_ms:
        print(f"\nFinal Best Makespan: {best_ms}")
        print(f"Time: {end_time - start_time:.2f}s")
        
        output_file = "solution_cp.txt"
        with open(output_file, 'w') as f:
            f.write(f"Instance: {instance_path}\n")
            f.write(f"Makespan: {best_ms}\n")
            f.write("Schedule:\n")
            for job in sorted(best_sched.keys()):
                f.write(f"{job} {best_sched[job]}\n")
        print(f"Solution written to {output_file}")
    else:
        print("No solution found within time limit.")

if __name__ == "__main__":
    main()
