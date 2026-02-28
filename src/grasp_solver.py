import sys
import os
import time
import random
import multiprocessing as mp

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.parser import RCPSPInstance
from src.sgs import SGS

def calculate_priorities(instance):
    """Pre-calculate various priority metrics for GRASP."""
    # 1. EST / LFT / Slack (Topological)
    est = {i: 0 for i in range(1, instance.num_jobs + 2)}
    for i in range(1, instance.num_jobs + 2):
        if i in instance.successors:
            for succ in instance.successors[i]:
                est[succ] = max(est[succ], est[i] + instance.durations[i])
                
    horizon = est[instance.num_jobs + 1] # Simple upper bound
    lst = {i: horizon for i in range(1, instance.num_jobs + 2)}
    lst[instance.num_jobs + 1] = est[instance.num_jobs + 1]
    for i in range(instance.num_jobs, 0, -1):
        if i in instance.successors and instance.successors[i]:
            lst[i] = min(lst[succ] - instance.durations[i] for succ in instance.successors[i])
            
    slack = {i: lst[i] - est[i] for i in range(1, instance.num_jobs + 1)}
    
    # 2. Most Immediate Successors (MIS)
    mis = {i: len(instance.successors.get(i, [])) for i in range(1, instance.num_jobs + 1)}
    
    # 3. Shortest/Longest Processing Time (SPT/LPT)
    durations = instance.durations
    
    # 4. Resource Usage
    res_usage = {}
    for i in range(1, instance.num_jobs + 1):
        res_usage[i] = sum(instance.requests[i]) * instance.durations[i]

    return est, lst, slack, mis, durations, res_usage

def grasp_worker(worker_id, instance_path, target_makespan, shared_best, stop_event):
    """Worker process that continuously generates and evaluates GRASP schedules."""
    instance = RCPSPInstance(instance_path)
    sgs = SGS(instance)
    
    priorities = calculate_priorities(instance)
    est, lst, slack, mis, durations, res_usage = priorities
    
    rules = ['LFT', 'EST', 'SLACK', 'MIS', 'LPT', 'RES']
    
    iterations = 0
    local_best = float('inf')
    
    # Pre-seed numpy's RNG per worker if sgs uses it, but we'll use standard random here for the RCL
    random.seed()
    
    while not stop_event.is_set():
        iterations += 1
        
        # 1. Randomly pick a priority rule
        rule = random.choice(rules)
        
        # 2. Randomly pick an alpha for the Restricted Candidate List (RCL)
        # alpha = 1.0 means purely greedy, alpha = 0.0 means purely random
        alpha = random.uniform(0.5, 0.95) 
        
        # Construct schedule using Parallel SGS but with RCL
        schedule = {1: 0}
        active = []
        eligible = set(instance.successors.get(1, []))
        completed = {1}
        
        time_now = 0
        rem_cap = list(instance.capacities)
        
        # We need a custom greedy builder here that supports RCL easily
        # For pure speed, we'll build a fast serial SGS with RCL
        
        assigned_jobs = [1]
        eligible_serial = set(instance.successors.get(1, []))
        completed_serial = {1}
        
        while len(assigned_jobs) < instance.num_jobs:
            current_eligible = list(eligible_serial)
            
            # Evaluate priority for eligible jobs
            scores = []
            for j in current_eligible:
                if rule == 'LFT': score = -lst[j] # We want min LFT, so negative is higher score prioritizing min
                elif rule == 'EST': score = -est[j]
                elif rule == 'SLACK': score = -slack[j]
                elif rule == 'MIS': score = mis[j]
                elif rule == 'LPT': score = durations[j]
                elif rule == 'RES': score = res_usage[j]
                scores.append((score, j))
                
            scores.sort(reverse=True) # Highest score first
            
            if not scores:
                break # Should not happen in valid instance
                
            max_score = scores[0][0]
            min_score = scores[-1][0]
            
            # Threshold for RCL
            threshold = min_score + alpha * (max_score - min_score)
            
            rcl = [j for s, j in scores if s >= threshold]
            
            # Pick a random job from RCL
            chosen_job = random.choice(rcl)
            
            assigned_jobs.append(chosen_job)
            completed_serial.add(chosen_job)
            eligible_serial.remove(chosen_job)
            
            if chosen_job in instance.successors:
                for succ in instance.successors[chosen_job]:
                    # Check if all predecessors of succ are completed
                    # Since we only have successors map, we implicitly know predecessors by checking if we have enough info
                    # Actually, we need a predecessor map for fast checking.
                    pass # We will do standard priority list generation, then standard SGS
                    
        # Okay, building a full custom SGS with RCL inline is slower in Python. 
        # Better approach: Generate a priority list string using RCL, then feed to existing fast `sgs.parallel_sgs(priority_list)`
        
        # Build priority list using RCL
        preds = {i: [] for i in range(1, instance.num_jobs + 1)}
        for i in range(1, instance.num_jobs + 1):
            if i in instance.successors:
                for succ in instance.successors[i]:
                    preds[succ].append(i)
                    
        priority_list = [1]
        eligible_list = set(instance.successors.get(1, []))
        completed_set = {1}
        
        while len(priority_list) < instance.num_jobs:
            current_elig = list(eligible_list)
            scores = []
            for j in current_elig:
                if rule == 'LFT': score = -lst[j] 
                elif rule == 'EST': score = -est[j]
                elif rule == 'SLACK': score = -slack[j]
                elif rule == 'MIS': score = mis[j]
                elif rule == 'LPT': score = durations[j]
                elif rule == 'RES': score = res_usage[j]
                scores.append((score, j))
                
            scores.sort(reverse=True)
            if not scores: break
            
            c_max = scores[0][0]
            c_min = scores[-1][0]
            threshold = c_min + alpha * (c_max - c_min)
            rcl = [j for s, j in scores if s >= threshold]
            
            nxt = random.choice(rcl)
            priority_list.append(nxt)
            completed_set.add(nxt)
            eligible_list.remove(nxt)
            
            if nxt in instance.successors:
                for succ in instance.successors[nxt]:
                    if all(p in completed_set for p in preds[succ]):
                        eligible_list.add(succ)
                        
        # 3. Evaluate the constructed priority list
        # priority_list is a chromosome.
        schedule, makespan = sgs.parallel_sgs(priority_list)
        
        # 4. Optional: Fast Local Improvement (FBI)
        # We perform FBI if the schedule is promising to compress it.
        if makespan <= min(local_best + 6, shared_best.value + 6):
            schedule, makespan = sgs.fbi(schedule)
        
        # 5. Check Results
        if makespan < local_best:
            local_best = makespan
        
        with shared_best.get_lock():
            if makespan < shared_best.value:
                shared_best.value = makespan
                print(f"[Worker {worker_id}] New Global Best: {makespan} (Rule: {rule}, Alpha: {alpha:.2f})")
                
                # Verify <= target and save
                if makespan <= target_makespan:
                    print(f"!!! TARGET ATTAINED BY WORKER {worker_id} !!!")
                    stop_event.set()
                    # Write immediately
                    with open(f"grasp_target_{makespan}.txt", 'w') as f:
                        f.write(f"Makespan: {makespan}\nSchedule:\n")
                        for j in sorted(schedule.keys()):
                            f.write(f"{j} {schedule[j]}\n")

def main():
    if len(sys.argv) < 3:
        print("Usage: python src/grasp_solver.py <instance_path> <target_makespan>")
        return
        
    instance_path = sys.argv[1]
    target_makespan = int(sys.argv[2])
    
    num_workers = mp.cpu_count()
    print(f"Starting GRASP Engine on {instance_path}")
    print(f"Target Makespan: <= {target_makespan}")
    print(f"Threads: {num_workers}")
    
    shared_best = mp.Value('i', 9999)
    stop_event = mp.Event()
    
    processes = []
    
    start_time = time.time()
    
    # Launch workers
    for i in range(num_workers):
        p = mp.Process(target=grasp_worker, args=(i, instance_path, target_makespan, shared_best, stop_event))
        p.start()
        processes.append(p)
        
    try:
        # Monitor
        while not stop_event.is_set():
            time.sleep(1)
            elap = time.time() - start_time
            if elap > 3600: # 1 hour limit to prevent infinite loops
                print("\nTime limit reached (1 hour). Terminating.")
                stop_event.set()
                break
                
    except KeyboardInterrupt:
        print("\nInterrupted by user. Terminating threads...")
        stop_event.set()
        
    # Wait for clean shutdown
    for p in processes:
        p.join()
        
    best_found = shared_best.value
    print(f"\nGRASP Engine Finished. Best Makespan Found: {best_found}")
    
    if best_found <= target_makespan:
        print(f"SUCCESS! Target {target_makespan} achieved. Check grasp_target_{best_found}.txt")
    else:
        print(f"FAILED to reach target {target_makespan}.")

if __name__ == "__main__":
    main()
