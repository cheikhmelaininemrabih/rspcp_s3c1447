import heapq

class SGS:
    def __init__(self, instance):
        self.instance = instance

    def serial_sgs(self, activity_list):
        # Serial SGS
        # activity_list: permutation of jobs
        # Schedule each job at earliest feasible time respecting precedence and resource constraints
        
        schedule = {1: 0} # Dummy start
        start_times = {}
        finish_times = {}
        
        # Resource usage profile (time -> [r1, r2...])
        resource_usage = {}
        
        # Precompute predecessors for faster lookup
        preds = self.instance.predecessors
        reqs = self.instance.requests
        durations = self.instance.durations
        capacities = self.instance.capacities
        num_res = self.instance.num_resources
        
        # We process jobs in the order of activity_list
        # But we can only schedule a job if all its predecessors are scheduled?
        # Standard Serial SGS iterates through eligible set.
        # But here activity_list IS the priority rule.
        # We iterate n times. At each step, pick the first job in activity_list that is eligible.
        # This is O(n^2).
        # Optimization: maintain eligible set.
        
        completed = {1}
        scheduled = {1}
        start_times[1] = 0
        finish_times[1] = 0
        
        # Eligible set based on completed
        eligible = set()
        # Initialize eligible
        unscheduled_preds = {j: len(preds[j]) for j in range(1, self.instance.num_jobs + 1)}
        for s in self.instance.successors[1]:
            unscheduled_preds[s] -= 1 # 1 is completed
            if unscheduled_preds[s] == 0:
                eligible.add(s)
        
        # Filter activity_list to remove 1 and N if present/handled
        # But we need to follow the priority of activity_list.
        # We can map job -> priority (index in list)
        priority = {job: i for i, job in enumerate(activity_list)}
        
        # Main loop
        for _ in range(self.instance.num_jobs - 1): # 1 is done
            # Pick best eligible
            # Job with lowest index in activity_list
            if not eligible:
                break
                
            best_job = min(eligible, key=lambda j: priority.get(j, float('inf')))
            
            # Schedule best_job
            # Earliest start = max(finish of predecessors)
            est = 0
            for p in preds[best_job]:
                if p in finish_times:
                    est = max(est, finish_times[p])
            
            dur = durations[best_job]
            r = reqs[best_job]
            
            # Find first feasible time >= est
            t = est
            while True:
                feasible = True
                for time_step in range(t, t + dur):
                    if time_step in resource_usage:
                        usage = resource_usage[time_step]
                        for k in range(num_res):
                            if usage[k] + r[k] > capacities[k]:
                                feasible = False; break
                    if not feasible: break
                
                if feasible:
                    # Book
                    for time_step in range(t, t + dur):
                        if time_step not in resource_usage:
                            resource_usage[time_step] = [0] * num_res
                        for k in range(num_res):
                            resource_usage[time_step][k] += r[k]
                    
                    start_times[best_job] = t
                    finish_times[best_job] = t + dur
                    scheduled.add(best_job)
                    completed.add(best_job) # In Serial SGS, scheduled = completed for precedence
                    eligible.remove(best_job)
                    
                    # Update eligible
                    for s in self.instance.successors[best_job]:
                        unscheduled_preds[s] -= 1
                        if unscheduled_preds[s] == 0:
                            eligible.add(s)
                    break
                else:
                    t += 1
                    
        makespan = finish_times.get(self.instance.num_jobs, 0)
        return start_times, makespan

    def parallel_sgs(self, activity_list):
        # Parallel SGS (Time-based)
        # Iterate through time.
        
        time = 0
        active_jobs = [] # (finish_time, job_id)
        completed = set()
        scheduled = set()
        start_times = {}
        
        # Start dummy
        start_times[1] = 0
        completed.add(1)
        scheduled.add(1)
        active_jobs.append((0, 1)) # Dummy finishes at 0
        
        eligible = set()
        unscheduled_preds = {j: len(self.instance.predecessors[j]) for j in range(1, self.instance.num_jobs + 1)}
        
        # Initialize eligible (successors of 1)
        # Note: 1 is in active_jobs, so it will be processed in loop
        
        # Priority map
        priority = {job: i for i, job in enumerate(activity_list)}
        
        current_usage = [0] * self.instance.num_resources
        
        while len(scheduled) < self.instance.num_jobs:
            # Advance time to next event
            active_jobs.sort(key=lambda x: x[0])
            
            # If no active jobs and not all scheduled -> deadlock or gap?
            if not active_jobs:
                if len(scheduled) < self.instance.num_jobs:
                     # This happens if eligible is empty but scheduled < n
                     # Could be due to cycle or bug
                     break
            
            # If nothing eligible at current time, jump to next finish
            # But we must check if any job finishes AT current time first
            
            if not eligible and active_jobs:
                 if active_jobs[0][0] > time:
                     time = active_jobs[0][0]
            
            # Process finishing jobs
            finished_now = []
            while active_jobs and active_jobs[0][0] <= time:
                ft, j = active_jobs.pop(0)
                # Release resources
                if j != 1: # Dummy has 0 reqs
                    reqs = self.instance.requests[j]
                    for r in range(self.instance.num_resources):
                        current_usage[r] -= reqs[r]
                
                # Update successors
                for s in self.instance.successors[j]:
                    unscheduled_preds[s] -= 1
                    if unscheduled_preds[s] == 0:
                        eligible.add(s)
            
            # Try to schedule eligible jobs
            # Sort by priority
            sorted_eligible = sorted(list(eligible), key=lambda x: priority.get(x, float('inf')))
            
            scheduled_in_step = []
            for job in sorted_eligible:
                reqs = self.instance.requests[job]
                feasible = True
                for r in range(self.instance.num_resources):
                    if current_usage[r] + reqs[r] > self.instance.capacities[r]:
                        feasible = False
                        break
                
                if feasible:
                    start_times[job] = time
                    duration = self.instance.durations[job]
                    active_jobs.append((time + duration, job))
                    scheduled.add(job)
                    scheduled_in_step.append(job)
                    for r in range(self.instance.num_resources):
                        current_usage[r] += reqs[r]
            
            for job in scheduled_in_step:
                eligible.remove(job)
                
            # If we scheduled something, we stay at same time to see if more fit?
            # Yes, we loop.
            # If we didn't schedule anything, we must advance time.
            if not scheduled_in_step:
                if active_jobs:
                    next_time = active_jobs[0][0]
                    if next_time > time:
                        time = next_time
                    else:
                        # Should not happen if we processed all <= time
                        # Unless 0 duration job added?
                        # 0 duration job: finishes at time.
                        # We must process it immediately.
                        # My logic: 0 dur job added to active_jobs with finish=time.
                        # Next loop, it is popped. Resources released. Successors added.
                        # So loop continues.
                        pass
                else:
                    break

        makespan = 0
        if start_times:
            makespan = max(start_times[j] + self.instance.durations[j] for j in start_times)
            
        return start_times, makespan

    def calculate_makespan(self, schedule):
        if not schedule: return float('inf')
        return max(schedule[j] + self.instance.durations[j] for j in schedule)

    def fbi(self, schedule):
        # Forward-Backward Improvement (Approximation)
        # 1. Sort jobs by start time (Start-Justification)
        sorted_start = sorted(schedule.keys(), key=lambda k: schedule[k])
        s1, ms1 = self.serial_sgs(sorted_start)
        
        # 2. Sort jobs by finish time (Completion-Justification attempt)
        # Note: Serial SGS with finish time ordering is a known heuristic
        sorted_finish = sorted(s1.keys(), key=lambda k: s1[k] + self.instance.durations[k])
        s2, ms2 = self.serial_sgs(sorted_finish)
        
        if ms2 < ms1:
            return s2, ms2
        return s1, ms1
