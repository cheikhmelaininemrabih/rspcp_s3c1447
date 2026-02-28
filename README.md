# RCPSP Solver Collection

This repository contains solvers for the **Resource-Constrained Project Scheduling Problem (RCPSP)**, designed to solve instances from the PSPLIB (e.g., j30, j60, j120).

It includes two distinct approaches:
1.  **Exact Solver**: A Constraint Programming approach using Google OR-Tools (CP-SAT).
2.  **Metaheuristic Solver**: A Genetic Algorithm implementation based on the work of S. Hartmann.

## Directory Structure

-   `solver.py`: The main exact solver script using CP-SAT.
-   `RCPSP_Genetic_Algorithm/`: Folder containing the Genetic Algorithm implementation.
    -   `GeneticAlgorithm.py`: Core GA logic.
    -   `driver.py`: Script to run the GA.
-   `j60.sm.tgz`: Dataset archive (example).

## Requirements

To run these solvers, you need Python 3 and the following dependencies:

```bash
pip install ortools matplotlib
```

## Usage

### 1. Exact Solver (CP-SAT)

The `solver.py` script uses the CP-SAT solver from Google OR-Tools. It models the RCPSP using interval variables and cumulative constraints.

**Command:**
```bash
python3 solver.py <path_to_instance.sm> [best_known_upper_bound]
```

**Example:**
```bash
python3 solver.py data/j60/j601_1.sm 100
```

If a solution is found, it prints the makespan and the status (OPTIMAL or FEASIBLE).

### 2. Genetic Algorithm

The Genetic Algorithm is located in the `RCPSP_Genetic_Algorithm` directory. It implements a competitive GA with a Schedule Generation Scheme (SGS).

**Command:**
```bash
cd RCPSP_Genetic_Algorithm
python3 driver.py
```

*Note: You may need to adjust the `driver.py` or `GeneticAlgorithm.py` files to point to your specific instance files.*

## Algorithms

### CP-SAT Approach (`solver.py`)
-   **Modeling**: Uses `NewIntervalVar` for tasks and `AddCumulative` for resource constraints.
-   **Objective**: Minimize the end time of the sink node (Makespan).
-   **Features**:
    -   Parses standard PSPLIB `.sm` format.
    -   Supports an optional upper bound to tighten the search horizon.
    -   Uses multi-threaded search (8 workers by default).

### Genetic Algorithm (`RCPSP_Genetic_Algorithm/`)
-   **Based on**: "A competitive genetic algorithm for resource-constrained project scheduling" by S. Hartmann.
-   **Encoding**: Activity list representation.
-   **Decoding**: Uses Serial Schedule Generation Scheme (SGS) or Parallel SGS.
-   **Operators**:
    -   Crossover: One-point crossover tailored for activity lists.
    -   Mutation: Swaps adjacent activities.
    -   Selection: Rank-based or Roulette-wheel.
