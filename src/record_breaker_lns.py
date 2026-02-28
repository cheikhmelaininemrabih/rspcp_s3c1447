import sys
import os
import time
import random
from ortools.sat.python import cp_model

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.parser import RCPSPInstance

def load_schedule(filepath):
    schedule = {}
    makespan = float('inf')
    with open(filepath, 'r') as f:
        start_parsing = False
        for line in f:
            if line.startswith("Makespan:"):
                makespan = int(line.split(":")[1].strip())
            if line.startswith("Schedule:"):
                start_parsing = True
                continue
            if start_parsing:
                parts = line.split()
                if len(parts) == 2:
                    schedule[int(parts[0])] = int(parts[1])
    return schedule, makespan

def save_schedule(filepath, schedule, makespan):
    with open(filepath, 'w') as f:
        f.write(f"Makespan: {makespan}\n")
        f.write("Schedule:\n")
        for job in sorted(schedule.keys()):
            f.write(f"{job} {schedule[job]}\n")

def get_job_slack(instance, schedule, makespan):
    """Calculate simple topological slack based on current schedule for heuristics."""
    lst = {i: makespan for i in range(1, instance.num_jobs + 2)}
    lst[instance.num_jobs + 1] = makespan
    
    for i in range(instance.num_jobs, 0, -1):
        min_succ_start = float('inf')
        if i not in instance.successors or not instance.successors[i]:
            min_succ_start = makespan
        else:
            for succ in instance.successors[i]:
                min_succ_start = min(min_succ_start, lst.get(succ, makespan))
        
        lst[i] = min_succ_start - instance.durations[i]
        
    slacks = {}
    for job, start in schedule.items():
        slacks[job] = lst.get(job, makespan) - start
    return slacks

def block_solve(instance, current_schedule, block_jobs, target_makespan, time_limit=10.0):
    """
    Solves a subproblem where only `block_jobs` can move.
    All other jobs are fixed to their `current_schedule` start times.
    Target: makespan < target_makespan (or <= if we want lateral movement).
    """
    model = cp_model.CpModel()
    
    # We constrain the horizon to the CURRENT makespan. We don't want worse.
    # Actually, we want BETTER. So horizon = target_makespan - 1
    horizon = target_makespan - 1
    
    starts = {}
    ends = {}
    intervals = {}
    demands = [[] for _ in range(instance.num_resources)]
    
    # Create variables
    for job in range(1, instance.num_jobs + 1):
        dur = instance.durations[job]
        
        if job in block_jobs:
            # Free variable within tight horizon
            start_var = model.NewIntVar(0, horizon, f'start_{job}')
            end_var = model.NewIntVar(0, horizon, f'end_{job}')
            
            # Hint from current schedule to speed up feasible finding
            # Just in case the hint isn't valid under new tight horizon, CP-SAT will ignore or fix it quickly.
            if current_schedule[job] <= horizon - dur:
                 model.AddHint(start_var, current_schedule[job])
        else:
            # Fixed variable!
            fixed_start = current_schedule[job]
            if fixed_start + dur > horizon:
                 # This block optimization attempt is impossible because fixed jobs leak past horizon
                 return None, False
            start_var = model.NewIntVar(fixed_start, fixed_start, f'start_{job}')
            end_var = model.NewIntVar(fixed_start + dur, fixed_start + dur, f'end_{job}')
            
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
            
    # Objective: Minimize makespan (or just find feasible since we tightened horizon)
    makespan_var = ends[instance.num_jobs]
    model.Minimize(makespan_var)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = False # Too noisy for thousands of runs
    solver.parameters.num_search_workers = 8 # Fast parallel internal search
    
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        new_ms = solver.Value(makespan_var)
        new_sched = {job: solver.Value(starts[job]) for job in range(1, instance.num_jobs + 1)}
        return new_sched, True
    
    return None, False

def generate_blocks(instance, schedule, slacks, makespan):
    blocks = []
    
    # 1. Time-window blocks: Group jobs starting in the same time segment
    for t_start in range(0, makespan, 15):
        t_end = t_start + 40 # Overlapping windows
        block = [j for j, start in schedule.items() if j != 1 and j != instance.num_jobs and t_start <= start < t_end]
        if 5 <= len(block) <= 25:
            blocks.append(("TimeWindow", block))
            
    # 2. Path-based blocks (Resource contention)
    # Group jobs that use the rarest/most contended resource
    for r in range(instance.num_resources):
        users = [j for j in range(2, instance.num_jobs) if instance.requests[j][r] > 0]
        # Just randomly sample from resource users
        for _ in range(5):
            if len(users) >= 15:
                # Sample jobs that are temporally close to each other
                pivot = random.choice(users)
                pivot_time = schedule[pivot]
                sorted_users = sorted(users, key=lambda x: abs(schedule[x] - pivot_time))
                block_size = random.randint(15, min(25, len(sorted_users)))
                blocks.append(("ResourceDense", sorted_users[:block_size]))
                
    # 3. Critical Path / Low Slack blocks
    critical = [j for j, sl in slacks.items() if sl < 5 and j != 1 and j != instance.num_jobs]
    for _ in range(10):
        if len(critical) > 0:
            pivot = random.choice(critical)
            pivot_time = schedule[pivot]
            
            # Form block around critical pivot
            candidates = [j for j in range(2, instance.num_jobs) if abs(schedule[j] - pivot_time) <= 30]
            if len(candidates) > 25:
                candidates = random.sample(candidates, 25)
                
            blocks.append(("CriticalCentered", candidates))
            
    # 4. Pure Random blocks
    for _ in range(20):
        pool = list(range(2, instance.num_jobs))
        size = random.randint(15, 25)
        blocks.append(("RandomSubset", random.sample(pool, size)))

    random.shuffle(blocks)
    return blocks

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/record_breaker_lns.py <instance_path> [start_solution.txt]")
        return
        
    instance_path = sys.argv[1]
    solution_file = sys.argv[2] if len(sys.argv) > 2 else "solution.txt"
    output_file = "record_broken_solution.txt"
    
    instance = RCPSPInstance(instance_path)
    
    print(f"Loading seed schedule from {solution_file}...")
    try:
        current_sched, current_ms = load_schedule(solution_file)
        if current_ms > 154:
            print(f"Warning: Starting makespan is {current_ms}. Expected 154.")
        else:
            print(f"Success! Starting from elite makespan: {current_ms}")
    except Exception as e:
        print(f"Fatal: Could not load initial schedule: {e}")
        return

    iteration = 0
    start_time = time.time()
    
    print(f"\n=============================================")
    print(f" STARTING EXTREME LNS. TARGET MAKESPAN: < {current_ms}")
    print(f"=============================================\n")
    
    while True:
        iteration += 1
        slacks = get_job_slack(instance, current_sched, current_ms)
        blocks = generate_blocks(instance, current_sched, slacks, current_ms)
        
        print(f"--- LNS Iteration {iteration} | Generated {len(blocks)} candidate blocks ---")
        
        for idx, (block_type, block_jobs) in enumerate(blocks):
            # To break the record, target makespan is current_ms 
            # (Remember block_solve limits horizon to target_makespan - 1)
            target = current_ms 
            
            new_sched, improved = block_solve(instance, current_sched, block_jobs, target, time_limit=5.0)
            
            if improved:
                # Validate New Makespan
                new_ms = max(new_sched[j] + instance.durations[j] for j in new_sched)
                
                if new_ms < current_ms:
                    print(f"\n!!! BREAKTHROUGH !!!")
                    print(f"Block Type: {block_type} | Block Size: {len(block_jobs)}")
                    print(f"Old Makespan: {current_ms} -> NEW MAKESPAN: {new_ms}")
                    
                    current_ms = new_ms
                    current_sched = new_sched
                    save_schedule(output_file, current_sched, current_ms)
                    print(f"Saved new world record to {output_file}\n")
                    
                    # Restart block generation around new topology
                    break
        
        elapsed = time.time() - start_time
        print(f"Completed LNS Iteration {iteration} | Time Elapsed: {elapsed:.2f}s | Current Best: {current_ms}")
        
        # Terminate? E.g. after 2 hours
        if elapsed > 7200:
            print("Time limit reached for Extreme LNS.")
            break

if __name__ == "__main__":
    main()
