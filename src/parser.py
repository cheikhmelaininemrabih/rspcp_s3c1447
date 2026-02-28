class RCPSPInstance:
    def __init__(self, filepath):
        self.filepath = filepath
        self.num_jobs = 0
        self.num_resources = 0
        self.durations = []  # 1-based index (0 is unused)
        self.requests = []   # 1-based index: requests[j] = [r1, r2, ...]
        self.successors = {} # 1-based index: successors[j] = [s1, s2, ...]
        self.predecessors = {}
        self.capacities = []
        self.parse()

    def parse(self):
        with open(self.filepath, 'r') as f:
            lines = f.readlines()

        mode = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith('***') or line.startswith('---'):
                continue
            
            if line.startswith('projects'):
                continue

            if 'jobs (incl. supersource/sink ):' in line:
                parts = line.split(':')
                self.num_jobs = int(parts[1].strip())
                # Initialize structures (1-based indexing)
                self.durations = [0] * (self.num_jobs + 1)
                self.requests = [[] for _ in range(self.num_jobs + 1)]
                self.successors = {i: [] for i in range(1, self.num_jobs + 1)}
                self.predecessors = {i: [] for i in range(1, self.num_jobs + 1)}
                continue

            if '- renewable' in line and ':' in line:
                 parts = line.split(':')
                 val = parts[1].strip().split()[0]
                 self.num_resources = int(val)
                 continue

            if line.startswith('PRECEDENCE RELATIONS:'):
                mode = 'PRECEDENCE'
                continue
            
            if line.startswith('REQUESTS/DURATIONS:'):
                mode = 'REQUESTS'
                continue

            if line.startswith('RESOURCEAVAILABILITIES:'):
                mode = 'RESOURCES'
                continue

            if mode == 'PRECEDENCE':
                if line.startswith('jobnr.'): continue
                parts = list(map(int, line.split()))
                if not parts: continue
                
                job_id = parts[0]
                # parts[1] is mode count, parts[2] is num successors
                succs = parts[3:]
                self.successors[job_id] = succs
                for s in succs:
                    if s not in self.predecessors: self.predecessors[s] = []
                    self.predecessors[s].append(job_id)

            elif mode == 'REQUESTS':
                if line.startswith('jobnr.') or line.startswith('-----'): continue
                parts = list(map(int, line.split()))
                if not parts: continue
                
                job_id = parts[0]
                # parts[1] is mode (usually 1)
                duration = parts[2]
                reqs = parts[3:] # Resource requirements R1 R2 ...
                
                self.durations[job_id] = duration
                self.requests[job_id] = reqs

            elif mode == 'RESOURCES':
                if line.startswith('R'): continue # R 1 R 2 ... header
                # The line contains capacities
                self.capacities = list(map(int, line.split()))
                mode = None # Done with resources

    def get_start_job(self):
        return 1

    def get_end_job(self):
        return self.num_jobs

    def __repr__(self):
        return f"RCPSPInstance(jobs={self.num_jobs}, res={self.num_resources})"
