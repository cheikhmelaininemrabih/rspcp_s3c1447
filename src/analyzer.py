import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.parser import RCPSPInstance

def analyze_schedule(instance_path, schedule_file):
    instance = RCPSPInstance(instance_path)
    schedule = {}
    with open(schedule_file, 'r') as f:
        start_parsing = False
        for line in f:
            if line.startswith("Schedule:"):
                start_parsing = True
                continue
            if start_parsing:
                parts = line.split()
                if len(parts) == 2:
                    schedule[int(parts[0])] = int(parts[1])
                    
    makespan = max(schedule[j] + instance.durations[j] for j in schedule)
    
    # Calculate resource utilization
    usage = {t: [0]*instance.num_resources for t in range(makespan)}
    for j in range(1, instance.num_jobs + 1):
        start = schedule[j]
        dur = instance.durations[j]
        reqs = instance.requests[j]
        for t in range(start, start + dur):
            for r in range(instance.num_resources):
                usage[t][r] += reqs[r]
                
    # Calculate average utilization per resource
    avg_utilization = [0] * instance.num_resources
    for r in range(instance.num_resources):
        total_used = sum(usage[t][r] for t in range(makespan))
        total_cap = makespan * instance.capacities[r]
        avg_utilization[r] = (total_used / total_cap) * 100 if total_cap > 0 else 0
        
    print(f"=== Analysis for {os.path.basename(instance_path)} ===")
    print(f"Makespan: {makespan}")
    for r in range(instance.num_resources):
        print(f"Resource {r+1} Avg Utilization: {avg_utilization[r]:.2f}% (Cap: {instance.capacities[r]})")
        
    # Find active periods vs fully idle periods
    idle_slots = 0
    for t in range(makespan):
        if all(usage[t][r] == 0 for r in range(instance.num_resources)):
            idle_slots += 1
            
    print(f"Global Idle Time Slots (No active jobs): {idle_slots}")

if __name__ == "__main__":
    analyze_schedule(sys.argv[1], sys.argv[2])
