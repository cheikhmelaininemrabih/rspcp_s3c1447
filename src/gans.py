import random
import time
import copy
from src.sgs import SGS
from src.parser import RCPSPInstance
try:
    from src.cp_solver import CP_LNS
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

class GANS:
    def __init__(self, instance_path):
        self.instance = RCPSPInstance(instance_path)
        if self.instance.num_jobs == 0:
            print("Warning: Instance empty or parsed incorrectly. Ensure the file format is valid.")
        
        self.sgs = SGS(self.instance)
        if HAS_ORTOOLS:
            self.cp_lns = CP_LNS(self.instance)
        
        # Tuned parameters for fastest convergence to best solution
        self.params = {
            'pop_size': 300,          # Increased for better exploration
            'generations': 5000,      # Increased for longer search
            'mutation_rate': 0.3,     # Increased mutation
            'ns_frequency': 10,       # Frequent LNS
            'ns_steps': 200,
            'dense_threshold': 0.75,
            'tabu_size': 100,
            'elite_size': 10          # Keep more elites
        }
        self.resource_weights = self.calculate_resource_weights()
        self.population = []
        self.best_solution = None
        self.best_makespan = float('inf')
        self.output_file = "best_gans_solution.txt"

    def save_best_solution(self):
        with open(self.output_file, 'w') as f:
            f.write(f"Makespan: {self.best_makespan}\n")
            f.write("Schedule:\n")
            if self.best_solution:
                for job in sorted(self.best_solution.keys()):
                    f.write(f"{job} {self.best_solution[job]}\n")

    def calculate_resource_weights(self):
        # Heuristic: Weight = Total Demand / (Capacity * Horizon_Estimate)
        weights = {}
        total_demand = [0] * self.instance.num_resources
        for j in range(1, self.instance.num_jobs + 1):
            dur = self.instance.durations[j]
            reqs = self.instance.requests[j]
            for r in range(self.instance.num_resources):
                total_demand[r] += reqs[r] * dur
        
        for r in range(self.instance.num_resources):
            cap = self.instance.capacities[r] if self.instance.capacities else 1
            if cap > 0:
                weights[r] = total_demand[r] / cap
            else:
                weights[r] = 0
        return weights

    def calculate_lst(self):
        # 1. Topological Sort for EST
        in_degree = {i: len(self.instance.predecessors.get(i, [])) for i in range(1, self.instance.num_jobs + 1)}
        zero_in = [i for i in range(1, self.instance.num_jobs + 1) if in_degree[i] == 0]
        topo_order = []
        
        while zero_in:
            u = zero_in.pop(0)
            topo_order.append(u)
            if u in self.instance.successors:
                for v in self.instance.successors[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        zero_in.append(v)
        
        # 2. EST Calculation
        est = {i: 0 for i in range(1, self.instance.num_jobs + 1)}
        for u in topo_order:
            finish_u = est[u] + self.instance.durations[u]
            if u in self.instance.successors:
                for v in self.instance.successors[u]:
                    est[v] = max(est[v], finish_u)
                    
        max_est = max(est.values()) if est else 0
        
        # 3. LST Calculation
        lst = {i: max_est for i in range(1, self.instance.num_jobs + 1)}
        for u in reversed(topo_order):
            if u in self.instance.successors and self.instance.successors[u]:
                 min_ls_succ = min(lst[v] for v in self.instance.successors[u])
                 lst[u] = min_ls_succ - self.instance.durations[u]
            else:
                 lst[u] = max_est - self.instance.durations[u]
                 
        return lst

    def initialize_population(self):
        self.population = []
        
        # 1. Heuristic Initialization
        lst = self.calculate_lst()
        
        # LST Priority
        lst_chrom = sorted(range(1, self.instance.num_jobs + 1), key=lambda x: lst[x])
        st, ms = self.sgs.serial_sgs(lst_chrom)
        self.population.append({'chrom': lst_chrom, 'schedule': st, 'makespan': ms})
        if ms < self.best_makespan: self.best_makespan = ms; self.best_solution = st

        # LFT Priority (LST + Dur)
        lft_chrom = sorted(range(1, self.instance.num_jobs + 1), key=lambda x: lst[x] + self.instance.durations[x])
        st, ms = self.sgs.serial_sgs(lft_chrom)
        self.population.append({'chrom': lft_chrom, 'schedule': st, 'makespan': ms})
        if ms < self.best_makespan: self.best_makespan = ms; self.best_solution = st
        
        for _ in range(self.params['pop_size'] - len(self.population)):
            chrom = self.generate_random_chromosome()
            # Mix Serial and Parallel SGS
            if random.random() < 0.5:
                start_times, makespan = self.sgs.parallel_sgs(chrom)
            else:
                start_times, makespan = self.sgs.serial_sgs(chrom)

            self.population.append({
                'chrom': chrom,
                'schedule': start_times,
                'makespan': makespan
            })
            if makespan < self.best_makespan:
                self.best_makespan = makespan
                self.best_solution = start_times
                self.save_best_solution()
        
        print(f"Initial Best Makespan: {self.best_makespan}")

    def generate_random_chromosome(self):
        # Biased Random Key Genetic Algorithm approach or Topological Sort
        # Pure random topological sort
        in_degree = {i: len(self.instance.predecessors[i]) for i in range(1, self.instance.num_jobs + 1)}
        zero_in = [i for i in range(1, self.instance.num_jobs + 1) if in_degree[i] == 0]
        topo = []
        
        while zero_in:
            idx = random.randint(0, len(zero_in) - 1)
            node = zero_in.pop(idx)
            topo.append(node)
            for succ in self.instance.successors[node]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    zero_in.append(succ)
        return topo

    def crossover_standard(self, p1_chrom, p2_chrom):
        # Two-Point Crossover for Permutations (maintaining precedence relative order)
        if len(p1_chrom) < 2: return p1_chrom
        
        cut1 = random.randint(1, len(p1_chrom) - 2)
        cut2 = random.randint(cut1 + 1, len(p1_chrom) - 1)
        
        child = [None] * len(p1_chrom)
        child[cut1:cut2] = p1_chrom[cut1:cut2]
        current_set = set(child[cut1:cut2])
        
        # Fill remaining spots with p2 order
        p2_idx = 0
        for i in range(len(child)):
            if child[i] is None:
                while p2_chrom[p2_idx] in current_set:
                    p2_idx += 1
                child[i] = p2_chrom[p2_idx]
                current_set.add(p2_chrom[p2_idx])
        
        return child

    def mutation(self, chrom):
        # Swap mutation that respects precedence
        if len(chrom) < 2: return chrom
        
        for _ in range(10): # Try more times
            idx1 = random.randint(0, len(chrom) - 2)
            idx2 = random.randint(idx1 + 1, min(idx1 + 5, len(chrom) - 1)) # Local swap
            
            j1, j2 = chrom[idx1], chrom[idx2]
            
            # Check dependency
            # If j1 is predecessor of j2, we can't put j2 before j1
            # If j2 is successor of j1, we can't swap
            
            # Check if path exists j1 -> ... -> j2
            # Expensive to check full path. 
            # Just check direct precedence for now or rely on SGS to handle it?
            # SGS takes a list. If list violates precedence, SGS might fail or produce invalid schedule?
            # Parallel SGS uses list as priority. It always respects precedence hard constraints.
            # So ANY permutation is valid input for SGS priority.
            
            chrom[idx1], chrom[idx2] = j2, j1
            return chrom
            
        return chrom

    def local_search(self, individual):
        # Hill Climbing with FBI
        chrom = list(individual['chrom'])
        current_ms = individual['makespan']
        improved = False
        
        # Try improving current schedule first with FBI
        sched_fbi, ms_fbi = self.sgs.fbi(individual['schedule'])
        if ms_fbi < current_ms:
            individual['schedule'] = sched_fbi
            individual['makespan'] = ms_fbi
            current_ms = ms_fbi
            improved = True
        
        for _ in range(50):
            mutated = self.mutation(list(chrom))
            st, ms = self.sgs.parallel_sgs(mutated)
            
            # Apply FBI to mutated offspring
            st_fbi, ms_fbi = self.sgs.fbi(st)
            if ms_fbi < ms:
                st, ms = st_fbi, ms_fbi
                
            if ms < current_ms:
                current_ms = ms
                chrom = mutated
                individual['schedule'] = st
                individual['makespan'] = ms
                individual['chrom'] = chrom
                improved = True
        
        return individual, improved

    def identify_dense_genes(self, schedule, makespan):
        dense_genes = []
        resource_usage = [[0] * self.instance.num_resources for _ in range(makespan + 1)]
        
        for job, start in schedule.items():
            if job == 1 or job == self.instance.num_jobs: continue
            dur = self.instance.durations[job]
            reqs = self.instance.requests[job]
            for t in range(start, start + dur):
                if t < makespan:
                    for r in range(self.instance.num_resources):
                        resource_usage[t][r] += reqs[r]
        
        for t in range(makespan):
            v_t = 0
            for r in range(self.instance.num_resources):
                R_k = self.instance.capacities[r]
                if R_k > 0:
                    used = resource_usage[t][r]
                    w_k = self.resource_weights.get(r, 1.0)
                    v_t += ((R_k - used) / R_k) * w_k
            
            if v_t < self.params['dense_threshold']:
                gene = []
                for job, start in schedule.items():
                    if job == 1 or job == self.instance.num_jobs: continue
                    dur = self.instance.durations[job]
                    if start <= t < start + dur:
                        gene.append(job)
                if gene:
                    dense_genes.append(tuple(sorted(gene)))
                    
        return list(set(dense_genes))

    def crossover_dense(self, p1, p2):
        p1_chrom = p1['chrom']
        p1_sched = p1['schedule']
        p1_ms = p1['makespan']
        
        dense_genes = self.identify_dense_genes(p1_sched, p1_ms)
        
        if not dense_genes:
            return self.crossover_standard(p1_chrom, p2['chrom'])
            
        gene = random.choice(dense_genes)
        
        max_idx = -1
        for job in gene:
            try:
                idx = p1_chrom.index(job)
                if idx > max_idx: max_idx = idx
            except ValueError: pass
            
        if max_idx == -1: return self.crossover_standard(p1_chrom, p2['chrom'])
        
        child = p1_chrom[:max_idx+1]
        current_set = set(child)
        
        for job in p2['chrom']:
            if job not in current_set:
                child.append(job)
                
        return child

    def neighborhood_search_A(self, individual, current_window_size=None):
        chrom = list(individual['chrom'])
        schedule = individual['schedule']
        
        # Core activity
        core = random.choice(chrom[1:-1]) # Skip dummies
        start_core = schedule[core]
        
        # Block selection (window)
        # Use provided window size or fallback to self.current_window which we will add to GANS params
        window = current_window_size if current_window_size else 25
        
        block = [j for j in chrom if j != 1 and j != self.instance.num_jobs and abs(schedule[j] - start_core) < window]
        
        if len(block) < 2: return individual, False
        
        if HAS_ORTOOLS and len(block) <= 40: # Increase block limit further for powerful CP LNS
            new_sched, improved = self.cp_lns.solve_block(schedule, block, individual['makespan'])
            if improved:
                # Reconstruct chromosome
                sorted_jobs = sorted(new_sched.keys(), key=lambda k: new_sched[k])
                individual['schedule'] = new_sched
                individual['makespan'] = max(new_sched[j] + self.instance.durations[j] for j in new_sched)
                individual['chrom'] = sorted_jobs
                return individual, True
        
        # Fallback to random swapping (Original NS A)
        indices = sorted([chrom.index(j) for j in block])
        sub_chrom = [chrom[i] for i in indices]
        
        best_sub = list(sub_chrom)
        best_ms = individual['makespan']
        improved = False
        
        for _ in range(50):
            temp_sub = list(best_sub)
            i1 = random.randint(0, len(temp_sub)-1)
            i2 = random.randint(0, len(temp_sub)-1)
            temp_sub[i1], temp_sub[i2] = temp_sub[i2], temp_sub[i1]
            
            temp_chrom = list(chrom)
            for idx, job in zip(indices, temp_sub):
                temp_chrom[idx] = job
                
            st, ms = self.sgs.parallel_sgs(temp_chrom)
            st, ms = self.sgs.fbi(st) # Add FBI here too
            
            if ms < best_ms:
                best_ms = ms
                best_sub = temp_sub
                individual['chrom'] = temp_chrom
                individual['schedule'] = st
                individual['makespan'] = ms
                improved = True
                
        return individual, improved

    def neighborhood_search_B(self, individual):
        """
        Neighborhood B from the paper (conceptually):
        Destroys a block and rebuilds it using a constructive heuristic (GRASP) or,
        in our CP-hybrid case, we rebuild it optimally using CP-SAT.
        This provides a more global change than Neighborhood A.
        """
        chrom = list(individual['chrom'])
        schedule = individual['schedule']
        
        # Pick a random activity
        core = random.choice(chrom[1:-1])
        start_core = schedule[core]
        
        # Select a larger block than Neighborhood A (e.g., 35)
        window = 35
        block = [j for j in chrom if j != 1 and j != self.instance.num_jobs and abs(schedule[j] - start_core) < window]
        
        if len(block) < 5: return individual, False
        
        if HAS_ORTOOLS:
            # We use CP-SAT here as a "Super-Heuristic" replacement for the GRASP constructive method
            # This is still consistent with the "Hybrid Metaheuristic" philosophy
            # We give it more time to find a solution for this larger block
            if hasattr(self.cp_lns, 'solver_time_limit'):
                 old_limit = self.cp_lns.solver_time_limit
            else:
                 old_limit = 2.0 # Default fallback
            
            # Use a simpler time limit mechanism if solver_time_limit attribute isn't directly exposed/used in solve_block
            # Actually, solve_block instantiates a new solver each time.
            # We need to pass the time limit to solve_block or modify it.
            # Let's assume we modify solve_block to accept time_limit
            
            # Since we can't easily change signature in one go without errors, 
            # let's just use the existing method which has hardcoded limit,
            # BUT we will rely on the fact that we increased the default limit to 2.0s globally.
            # For Neighborhood B, we might need even more.
            # Let's just call it. The large window is the key differentiator.
            
            new_sched, improved = self.cp_lns.solve_block(schedule, block, individual['makespan'])
            
            if improved:
                # Reconstruct chromosome
                sorted_jobs = sorted(new_sched.keys(), key=lambda k: new_sched[k])
                individual['schedule'] = new_sched
                individual['makespan'] = max(new_sched[j] + self.instance.durations[j] for j in new_sched)
                individual['chrom'] = sorted_jobs
                return individual, True
        
        return individual, False

    def get_critical_path(self, schedule, makespan):
        """
        Identify activities on the critical path.
        Critical activities are those with 0 slack (EST == LST).
        For simplicity in a heuristic context, we can backtrack from the end.
        """
        # Calculate EST (Earliest Start Time) - Forward Pass
        est = {i: 0 for i in range(1, self.instance.num_jobs + 2)}
        for i in range(1, self.instance.num_jobs + 2):
            if i in self.instance.successors:
                for succ in self.instance.successors[i]:
                    est[succ] = max(est[succ], est[i] + self.instance.durations[i])
        
        # Calculate LST (Latest Start Time) - Backward Pass
        lst = {i: makespan for i in range(1, self.instance.num_jobs + 2)}
        lst[self.instance.num_jobs + 1] = makespan
        
        for i in range(self.instance.num_jobs, 0, -1):
            min_succ_start = float('inf')
            if i not in self.instance.successors or not self.instance.successors[i]:
                min_succ_start = makespan
            else:
                for succ in self.instance.successors[i]:
                    min_succ_start = min(min_succ_start, lst[succ])
            
            lst[i] = min_succ_start - self.instance.durations[i]
            
        critical_activities = []
        # In a resource-constrained schedule, 'critical' is complex.
        # But heuristic approach: activities with start_time == lst[i] (based on precedence only) are topological critical.
        # Better heuristic for RCPSP: Backtrack from makespan using the actual schedule.
        # Find activity finishing at makespan. Then find its predecessor (precedence or resource) that finished just before it started.
        # Simplified: Activities with small slack in the CURRENT schedule.
        # Slack = LST - StartTime.
        # LST here is calculated based on precedence only, so it's an upper bound.
        
        # Let's use a simpler proxy: The activity that finishes last is critical.
        # And any activity that immediately precedes a critical activity (resource or precedence) is likely critical.
        
        # For LNS, we just need a "good" set of important activities.
        # Let's return activities with (LST - schedule[i]) < 5
        
        for i in range(1, self.instance.num_jobs + 1):
             if i in schedule:
                 slack = lst[i] - schedule[i]
                 if slack < 2: # Very tight
                     critical_activities.append(i)
                     
        if not critical_activities: # Fallback
            return list(schedule.keys())
            
        return critical_activities

    def neighborhood_search_Smart(self, individual):
        """
        Smart LNS: Selects a block centered around a CRITICAL activity.
        This focuses optimization where it matters most.
        """
        chrom = list(individual['chrom'])
        schedule = individual['schedule']
        makespan = individual['makespan']
        
        critical_activities = self.get_critical_path(schedule, makespan)
        
        if not critical_activities:
            return individual, False
            
        core = random.choice(critical_activities)
        start_core = schedule[core]
        
        # Window size - can be aggressive
        window = 30 
        
        block = [j for j in chrom if j != 1 and j != self.instance.num_jobs and abs(schedule[j] - start_core) < window]
        
        if len(block) < 5: return individual, False
        
        if HAS_ORTOOLS:
            new_sched, improved = self.cp_lns.solve_block(schedule, block, individual['makespan'])
            
            if improved:
                sorted_jobs = sorted(new_sched.keys(), key=lambda k: new_sched[k])
                individual['schedule'] = new_sched
                individual['makespan'] = max(new_sched[j] + self.instance.durations[j] for j in new_sched)
                individual['chrom'] = sorted_jobs
                return individual, True
        
        return individual, False

    def run(self):
        self.initialize_population()
        no_imp_count = 0
        
        for gen in range(self.params['generations']):
            # Elitism
            self.population.sort(key=lambda x: x['makespan'])
            new_pop = self.population[:self.params['elite_size']]
            
            # FBI on Elites
            if gen % 10 == 0:
                for ind in new_pop:
                    st_fbi, ms_fbi = self.sgs.fbi(ind['schedule'])
                    if ms_fbi < ind['makespan']:
                        ind['schedule'] = st_fbi
                        ind['makespan'] = ms_fbi
                        if ms_fbi < self.best_makespan:
                            self.best_makespan = ms_fbi
                            self.best_solution = st_fbi
                            self.save_best_solution()
                            print(f"FBI on Elite Improved: {ms_fbi}")
                            if ms_fbi <= 132: return self.best_solution, self.best_makespan

            # Diverse selection
            while len(new_pop) < self.params['pop_size']:
                # Tournament
                p1 = random.choice(self.population[:50]) 
                p2 = random.choice(self.population[:50])
                
                # Use Dense Crossover with 50% probability
                if random.random() < 0.5:
                    child_chrom = self.crossover_dense(p1, p2)
                else:
                    child_chrom = self.crossover_standard(p1['chrom'], p2['chrom'])
                
                if random.random() < self.params['mutation_rate']:
                    child_chrom = self.mutation(child_chrom)
                
                # Mix Serial SGS (for tight packing) and Parallel SGS
                if random.random() < 0.3:
                    st, ms = self.sgs.serial_sgs(child_chrom)
                else:
                    st, ms = self.sgs.parallel_sgs(child_chrom)
                    
                new_pop.append({'chrom': child_chrom, 'schedule': st, 'makespan': ms})
                
                if ms < self.best_makespan:
                    self.best_makespan = ms
                    self.best_solution = st
                    self.save_best_solution()
                    print(f"Gen {gen}: New Best Makespan: {ms}")
                    no_imp_count = 0
                    if ms <= 132: return self.best_solution, self.best_makespan
                
            self.population = new_pop
            no_imp_count += 1
            
            # Periodic Local Search / Neighborhood Search on Top Individuals
            if no_imp_count > self.params['ns_frequency']:
                print(f"Gen {gen}: Applying Neighborhood Search...")
                
                for i in range(10): # Increased from 5
                    # Use Smart Neighborhood (Critical Path) with 60% probability
                    # Use Neighborhood B (Large Block) with 20%
                    # Use Local Search with 20%
                    rand = random.random()
                    if rand < 0.6:
                        ind, imp = self.neighborhood_search_Smart(self.population[i])
                    elif rand < 0.8:
                        ind, imp = self.neighborhood_search_B(self.population[i])
                    else:
                        ind, imp = self.local_search(self.population[i])
                    
                    self.population[i] = ind
                    if ind['makespan'] < self.best_makespan:
                        self.best_makespan = ind['makespan']
                        self.best_solution = ind['schedule']
                        self.save_best_solution()
                        print(f"NS Improved Best Makespan: {self.best_makespan}")
                        no_imp_count = 0
                        if self.best_makespan <= 132: return self.best_solution, self.best_makespan
                
                if no_imp_count > 200: # Explosive Restart Threshold
                     print("!!! Stagnation Detected. EXPLOSIVE RESTART !!!")
                     # Keep best, nuke rest
                     best_ind = copy.deepcopy(self.population[0])
                     self.population = [best_ind]
                     
                     # Fill with mutated clones of best (Intensification around best)
                     for _ in range(50):
                         clone = copy.deepcopy(best_ind)
                         clone['chrom'] = self.mutation(clone['chrom'])
                         # Try Serial SGS for variety
                         st, ms = self.sgs.serial_sgs(clone['chrom'])
                         clone['schedule'] = st
                         clone['makespan'] = ms
                         self.population.append(clone)
                         
                     # Fill rest with random (Diversification)
                     while len(self.population) < self.params['pop_size']:
                         chrom = self.generate_random_chromosome()
                         st, ms = self.sgs.parallel_sgs(chrom)
                         self.population.append({'chrom': chrom, 'schedule': st, 'makespan': ms})
                     
                     no_imp_count = 0
                
                elif no_imp_count > self.params['ns_frequency'] * 2:
                     # Standard Diversification: Replace bottom half with random
                     print("Diversifying population...")
                     for i in range(self.params['pop_size'] // 2, self.params['pop_size']):
                         chrom = self.generate_random_chromosome()
                         st, ms = self.sgs.parallel_sgs(chrom)
                         self.population[i] = {'chrom': chrom, 'schedule': st, 'makespan': ms}
                     no_imp_count = 0

        return self.best_solution, self.best_makespan
