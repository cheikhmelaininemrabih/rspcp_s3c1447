import sys
import os
import time
from ortools.sat.python import cp_model

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.parser import RCPSPInstance

def solve_full_cp(instance_path, initial_solution_path, target_makespan):
    print(f"Loading instance: {instance_path}")
    instance = RCPSPInstance(instance_path)
    
    # Load initial solution
    initial_schedule = {}
    if initial_solution_path and os.path.exists(initial_solution_path):
        print(f"Loading initial solution from: {initial_solution_path}")
        with open(initial_solution_path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 2 and parts[0].isdigit():
                    initial_schedule[int(parts[0])] = int(parts[1])
    else:
        print("No initial solution found. Starting from scratch.")
                
    # if not initial_schedule:
    #    print("Failed to load initial schedule.")
    #    # return # Continue without hints if failed

    print(f"Building CP Model...")
    model = cp_model.CpModel()
    
    horizon = sum(instance.durations) # Safe upper bound
    starts = {}
    ends = {}
    intervals = {}
    demands = [[] for _ in range(instance.num_resources)]
    
    # 1. Variables
    for j in range(1, instance.num_jobs + 1):
        dur = instance.durations[j]
        start_var = model.NewIntVar(0, horizon, f'start_{j}')
        end_var = model.NewIntVar(0, horizon, f'end_{j}')
        interval_var = model.NewIntervalVar(start_var, dur, end_var, f'interval_{j}')
        
        starts[j] = start_var
        ends[j] = end_var
        intervals[j] = interval_var
        
        # Initial Solution Hinting (Warm Start)
        if j in initial_schedule:
            model.AddHint(start_var, initial_schedule[j])
            
        reqs = instance.requests[j]
        for r in range(instance.num_resources):
            if reqs[r] > 0:
                demands[r].append((interval_var, reqs[r]))

    # 2. Precedence Constraints
    for i in range(1, instance.num_jobs + 1):
        for succ in instance.successors[i]:
            model.Add(starts[succ] >= ends[i])
            
    # 3. Resource Constraints
    for r in range(instance.num_resources):
        cap = instance.capacities[r]
        if demands[r]:
            intervals_r = [d[0] for d in demands[r]]
            reqs_r = [d[1] for d in demands[r]]
            model.AddCumulative(intervals_r, reqs_r, cap)
            
    # 4. Objective & Target
    # Domain [target_makespan, horizon_upper_bound]
    # User said best known is 120. So let's search [112, 120].
    
    # We'll use 120 as the upper bound for the variables.
    current_best = 120 
    
    # If we find 120, good. If we find better, great.
    makespan_var = model.NewIntVar(target_makespan, current_best, 'makespan')
    model.AddMaxEquality(makespan_var, [ends[j] for j in range(1, instance.num_jobs + 1)])
    
    for j in range(1, instance.num_jobs + 1):
        model.Add(starts[j] <= current_best)
    
    model.Minimize(makespan_var)
    
    # 5. Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3600.0   # 1 hour
    solver.parameters.num_search_workers = 0          # 0 = auto-detect all CPUs
    solver.parameters.log_search_progress = True
    solver.parameters.cp_model_presolve = True
    # solver.parameters.linearization_level = 2 # Default is robust enough
    
    # Callback to print improvements
    class ProgressCallback(cp_model.CpSolverSolutionCallback):
        def __init__(self):
            cp_model.CpSolverSolutionCallback.__init__(self)
            
        def on_solution_callback(self):
            val = self.ObjectiveValue()
            print(f"New Best: {val}")
            
    callback = ProgressCallback()
    
    print(f"Starting solver with target makespan <= {target_makespan}...")
    status = solver.Solve(model, callback)
    
    print(f"Solver Status: {solver.StatusName(status)}")
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        new_ms = solver.Value(makespan_var)
        print(f"SUCCESS! Found solution with makespan: {new_ms}")
        
        new_schedule = {}
        for j in range(1, instance.num_jobs + 1):
            new_schedule[j] = solver.Value(starts[j])
            
        # Write to solution file
        output_file = "solution_cp.txt"
        with open(output_file, 'w') as f:
            f.write(f"Instance: {instance_path}\n")
            f.write(f"Makespan: {new_ms}\n")
            f.write("Schedule:\n")
            for job in sorted(new_schedule.keys()):
                f.write(f"{job} {new_schedule[job]}\n")
        print(f"Solution written to {output_file}")
    else:
        print("No better solution found within time limit.")

if __name__ == "__main__":
    # Solving j6013_8.sm
    # LB = 112, Best Known = 120
    # Target = 112 (Try to find optimal!)
    solve_full_cp(
        os.path.join(os.path.dirname(__file__), '../j6013_8.sm'),
        None, # No warm start
        112   # Target: Lower Bound
    )
