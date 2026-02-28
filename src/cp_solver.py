from ortools.sat.python import cp_model

class CP_LNS:
    def __init__(self, instance):
        self.instance = instance

    def solve_block(self, current_schedule, block_activities, horizon, time_limit=2.0):
        """
        Re-optimizes a block of activities using CP-SAT, keeping others fixed.
        """
        model = cp_model.CpModel()
        
        starts = {}
        ends = {}
        intervals = {}
        demands = []
        for r in range(self.instance.num_resources):
            demands.append([]) 
            
        # Create variables for block activities
        for job in block_activities:
            dur = self.instance.durations[job]
            start_var = model.NewIntVar(0, horizon, f'start_{job}')
            end_var = model.NewIntVar(0, horizon, f'end_{job}')
            interval_var = model.NewIntervalVar(start_var, dur, end_var, f'interval_{job}')
            
            starts[job] = start_var
            ends[job] = end_var
            intervals[job] = interval_var
            
            reqs = self.instance.requests[job]
            for r in range(self.instance.num_resources):
                if reqs[r] > 0:
                    demands[r].append((interval_var, reqs[r]))

        # Fixed activities
        for job in range(1, self.instance.num_jobs + 1):
            if job not in block_activities:
                if job in current_schedule:
                    start_val = current_schedule[job]
                    dur = self.instance.durations[job]
                    
                    interval_var = model.NewFixedSizeIntervalVar(start_val, dur, f'fixed_{job}')
                    reqs = self.instance.requests[job]
                    for r in range(self.instance.num_resources):
                        if reqs[r] > 0:
                            demands[r].append((interval_var, reqs[r]))
        
        # Precedence
        for i in range(1, self.instance.num_jobs + 1):
            for succ in self.instance.successors[i]:
                if i in block_activities and succ in block_activities:
                    model.Add(starts[succ] >= ends[i])
                elif i not in block_activities and succ in block_activities:
                    finish_i = current_schedule[i] + self.instance.durations[i]
                    model.Add(starts[succ] >= finish_i)
                elif i in block_activities and succ not in block_activities:
                    start_succ = current_schedule[succ]
                    model.Add(ends[i] <= start_succ)
                    
        # Resource Constraints
        for r in range(self.instance.num_resources):
            cap = self.instance.capacities[r]
            if demands[r]:
                intervals_r = [d[0] for d in demands[r]]
                reqs_r = [d[1] for d in demands[r]]
                model.AddCumulative(intervals_r, reqs_r, cap)
                
        # Objective: Minimize max end time of block activities (locally)
        # To truly improve global makespan, we should probably allow successors to move?
        # But for strict Neighborhood A, we fix others.
        if block_activities:
            obj_var = model.NewIntVar(0, horizon, 'makespan')
            model.AddMaxEquality(obj_var, [ends[j] for j in block_activities])
            model.Minimize(obj_var)
        
        solver = cp_model.CpSolver()
        # Increased time limit for deeper search in large blocks
        solver.parameters.max_time_in_seconds = time_limit
        status = solver.Solve(model)
        
        new_schedule = current_schedule.copy()
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            for job in block_activities:
                new_schedule[job] = solver.Value(starts[job])
            return new_schedule, True
        
        return current_schedule, False
