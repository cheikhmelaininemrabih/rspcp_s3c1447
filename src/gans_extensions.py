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

    def neighborhood_search_A(self, individual):
        # NS Type A: Time Window Optimization
        # 1. Select block of activities
        # 2. Unschedule them
        # 3. Calculate EST/LFT windows
        # 4. Reschedule optimally
        
        # Simplified implementation:
        # Just random shuffle of a sub-segment of chromosome that corresponds to a time window?
        # Actually, NS A operates on the schedule directly.
        # But we need to maintain a valid chromosome for the population.
        # So we operate on chromosome: 
        # Find a segment in chromosome that maps to a "block" in time.
        # Shuffle it?
        
        # Better: Select a "Core Activity" j.
        # Identify block: activities starting close to j.
        # Extract these from chromosome.
        # Re-insert them in a better order (local search on the sub-permutation).
        
        chrom = list(individual['chrom'])
        schedule = individual['schedule']
        
        # Core activity
        core = random.choice(chrom[1:-1]) # Skip dummies
        start_core = schedule[core]
        
        # Block
        window = 10
        block = [j for j in chrom if j != 1 and j != self.instance.num_jobs and abs(schedule[j] - start_core) < window]
        
        if len(block) < 2: return individual, False
        
        # Extract block from chrom
        indices = sorted([chrom.index(j) for j in block])
        sub_chrom = [chrom[i] for i in indices]
        
        # Local search on sub_chrom
        best_sub = list(sub_chrom)
        best_ms = individual['makespan']
        improved = False
        
        for _ in range(20):
            # Swap in sub_chrom
            temp_sub = list(best_sub)
            i1 = random.randint(0, len(temp_sub)-1)
            i2 = random.randint(0, len(temp_sub)-1)
            temp_sub[i1], temp_sub[i2] = temp_sub[i2], temp_sub[i1]
            
            # Reconstruct full chromosome
            temp_chrom = list(chrom)
            for idx, job in zip(indices, temp_sub):
                temp_chrom[idx] = job
                
            # Evaluate
            # Check precedence first? SGS Parallel handles it.
            st, ms = self.sgs.parallel_sgs(temp_chrom)
            if ms < best_ms:
                best_ms = ms
                best_sub = temp_sub
                individual['chrom'] = temp_chrom
                individual['schedule'] = st
                individual['makespan'] = ms
                improved = True
                
        return individual, improved
