import sys
import os
import time

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.parser import RCPSPInstance
from src.gans import GANS

def main():
    if len(sys.argv) > 1:
        instance_path = sys.argv[1]
    else:
        instance_path = os.path.join(os.path.dirname(__file__), '../j6029_6.sm')
    
    if not os.path.exists(instance_path):
         print(f"Error: Instance file {instance_path} not found.")
         return

    print(f"Solving instance: {instance_path}")
    
    try:
        optimizer = GANS(instance_path)
    except Exception as e:
        print(f"Error parsing instance: {e}")
        return
        
    start_time = time.time()
    best_schedule, best_makespan = optimizer.run()
    end_time = time.time()
    
    print(f"Best Makespan Found: {best_makespan}")
    print(f"Time: {end_time - start_time:.2f}s")
    
    output_file = "solution.txt"
    with open(output_file, 'w') as f:
        f.write(f"Instance: {instance_path}\n")
        f.write(f"Makespan: {best_makespan}\n")
        f.write("Schedule:\n")
        if best_schedule:
            for job in sorted(best_schedule.keys()):
                f.write(f"{job} {best_schedule[job]}\n")
            
    print(f"Solution written to {output_file}")


if __name__ == "__main__":
    main()
