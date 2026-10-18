import argparse
import os
import time

from benchmark_utils import (
    TIME_LIMIT_SECONDS,
    read_board_sizes,
    read_terminal_statuses,
    run_with_timeout,
    save_results,
)

def valid(board, n):
    if n < 1 or board is None or len(board) != n:
        return False
    return (all(isinstance(c, int) and 0 <= c < n for c in board)
            and len(set(board)) == n
            and len({board[r] + r for r in range(n)}) == n
            and len({board[r] - r for r in range(n)}) == n)


def _normalize_status(status, valid_solution, infeasible):
    if valid_solution:
        return "SAT"
    if infeasible:
        return "UNSAT"
    return status


def solve_cpsat(n):
    from ortools.sat.python import cp_model

    if n < 1:
        raise ValueError("n must be >= 1")

    start = time.perf_counter()

    model = cp_model.CpModel()

    q = [model.new_int_var(0, n - 1, f"q{r}") for r in range(n)]

    model.add_all_different(q)
    model.add_all_different([q[r] + r for r in range(n)])
    model.add_all_different([q[r] - r for r in range(n)])

    encoding_time = time.perf_counter() - start
    
    solver = cp_model.CpSolver()
    solve_start = time.perf_counter()
    status_code = solver.solve(model)
    solve_time = time.perf_counter() - solve_start

    runtime = encoding_time + solve_time

    status = solver.status_name(status_code)

    if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        board = [solver.value(q[r]) for r in range(n)]
        valid_solution = valid(board, n)
    else:
        board = None
        valid_solution = False

    status = _normalize_status(
        status,
        valid_solution,
        status_code == cp_model.INFEASIBLE,
    )

    return {
    "status": status,
    "board": board,
    "runtime_seconds": runtime,
    "valid_solution": valid_solution,
    "variables": n,
    "clauses": 0,
    "encoding_time": encoding_time,
    "solve_time": solve_time,
    }

def solve_cplex_cp(n):
    from docplex.cp.model import CpoModel

    if n < 1:
        raise ValueError("N must be >= 1")

    encoding_start = time.perf_counter()

    model = CpoModel()

    q = [model.integer_var(min=0, max=n - 1, name=f"q_{r}")
         for r in range(n)]

    model.add(model.all_diff(q))

    model.add(model.all_diff([q[r] + r for r in range(n)]))
    model.add(model.all_diff([q[r] - r for r in range(n)]))

    encoding_time = time.perf_counter() - encoding_start
    solve_start = time.perf_counter()
    solution = model.solve()
    solve_time = time.perf_counter() - solve_start

    runtime = encoding_time + solve_time

    board = None
    status = "NO_SOLUTION"
    valid_solution = False

    if solution is not None:
        try:
            candidate = [
                solution.get_value(q[r])
                for r in range(n)
            ]

            if valid(candidate, n):
                board = candidate
                valid_solution = True

            status = str(solution.get_solve_status())

        except (ValueError, TypeError, RuntimeError):
            board = None
            valid_solution = False
            status = "NO_VALID_SOLUTION"

    status = _normalize_status(
        status,
        valid_solution,
        "infeasible" in status.lower(),
    )

    return {
    "status": status,
    "board": board,
    "runtime_seconds": runtime,
    "valid_solution": valid_solution,
    "variables": n,
    "clauses": 0,
    "encoding_time": encoding_time,
    "solve_time": solve_time,
    }




def solve_cplex_mip(n):
    import cplex

    if n < 1:
        raise ValueError("n must be >= 1")

    encoding_start = time.perf_counter()

    model = cplex.Cplex()
    model.set_log_stream(None)
    model.set_error_stream(None)
    model.set_warning_stream(None)
    model.set_results_stream(None)

    model.objective.set_sense(model.objective.sense.minimize)

    names = [f"x_{r}_{c}" for r in range(n) for c in range(n)]
    model.variables.add(
        names=names,
        types=[model.variables.type.binary] * (n * n),
    )

    idx = lambda r, c: r * n + c

    rows, senses, rhs = [], [], []

    for r in range(n):
        rows.append(
            cplex.SparsePair(
                ind=[idx(r, c) for c in range(n)],
                val=[1.0] * n,
            )
        )
        senses.append("E")
        rhs.append(1.0)

    for c in range(n):
        rows.append(
            cplex.SparsePair(
                ind=[idx(r, c) for r in range(n)],
                val=[1.0] * n,
            )
        )
        senses.append("E")
        rhs.append(1.0)

    descending_diagonals = {}
    ascending_diagonals = {}
    for r in range(n):
        for c in range(n):
            descending_diagonals.setdefault(r - c, []).append(idx(r, c))
            ascending_diagonals.setdefault(r + c, []).append(idx(r, c))

    for diagonal in (*descending_diagonals.values(), *ascending_diagonals.values()):
        if len(diagonal) > 1:
            rows.append(cplex.SparsePair(ind=diagonal, val=[1.0] * len(diagonal)))
            senses.append("L")
            rhs.append(1.0)

    model.linear_constraints.add(
        lin_expr=rows,
        senses="".join(senses),
        rhs=rhs,
    )

    encoding_time = time.perf_counter() - encoding_start
    solve_start = time.perf_counter()
    model.solve()
    solve_time = time.perf_counter() - solve_start
    runtime = encoding_time + solve_time

    status = model.solution.get_status_string()
    status_code = model.solution.get_status()

    board = None
    if model.solution.is_primal_feasible():
        values = model.solution.get_values()
        board = []

        for r in range(n):
            cols = [
                c for c in range(n)
                if values[idx(r, c)] > 0.5
            ]
            if len(cols) != 1:
                board = None
                break
            board.append(cols[0])

    valid_solution = board is not None and valid(board, n)
    status = _normalize_status(
        status,
        valid_solution,
        "infeasible" in status.lower(),
    )
    model.end()

    return {
    "status": status,
    "board": board,
    "runtime_seconds": runtime,
    "valid_solution": valid_solution,
    "variables": n * n,
    "clauses": 0,
    "encoding_time": encoding_time,
    "solve_time": solve_time,
    }


def solve_gurobi(n):
    import gurobipy as gp
    from gurobipy import GRB

    if n < 1:
        raise ValueError("n must be >= 1")

    wls_params = {
        "WLSACCESSID": os.environ.get("GRB_WLSACCESSID"),
        "WLSSECRET": os.environ.get("GRB_WLSSECRET"),
        "LICENSEID": os.environ.get("GRB_LICENSEID"),
    }
    configured_params = {
        name: value for name, value in wls_params.items() if value
    }
    if configured_params and len(configured_params) != len(wls_params):
        missing_params = sorted(set(wls_params) - configured_params.keys())
        raise RuntimeError(
            "Incomplete Gurobi WLS configuration. Set environment variables: "
            + ", ".join(f"GRB_{name}" for name in missing_params)
        )

    if configured_params:
        try:
            configured_params["LICENSEID"] = int(configured_params["LICENSEID"])
        except ValueError as error:
            raise ValueError("GRB_LICENSEID must be an integer") from error

        with gp.Env(params=configured_params) as env:
            return _solve_gurobi_model(gp, GRB, n, env)

    return _solve_gurobi_model(gp, GRB, n)


def _solve_gurobi_model(gp, GRB, n, env=None):
    encoding_start = time.perf_counter()

    with gp.Model("nqueens", env=env) as model:
        model.Params.OutputFlag = 0

        x = model.addVars(n, n, vtype=GRB.BINARY, name="x")

        for r in range(n):
            model.addConstr(
                gp.quicksum(x[r, c] for c in range(n)) == 1
            )

        for c in range(n):
            model.addConstr(
                gp.quicksum(x[r, c] for r in range(n)) == 1
            )

        for r1 in range(n):
            for c1 in range(n):
                for r2 in range(r1 + 1, n):
                    for c2 in (c1 + (r2 - r1), c1 - (r2 - r1)):
                        if 0 <= c2 < n:
                            model.addConstr(x[r1, c1] + x[r2, c2] <= 1)

        model.setObjective(0, GRB.MINIMIZE)
        encoding_time = time.perf_counter() - encoding_start
        solve_start = time.perf_counter()
        model.optimize()
        solve_time = time.perf_counter() - solve_start
        runtime = encoding_time + solve_time

        status_map = {
            GRB.OPTIMAL: "OPTIMAL",
            GRB.INFEASIBLE: "INFEASIBLE",
            GRB.TIME_LIMIT: "TIME_LIMIT",
            GRB.INTERRUPTED: "INTERRUPTED",
            GRB.SUBOPTIMAL: "SUBOPTIMAL",
        }
        status = status_map.get(
            model.Status, f"STATUS_{model.Status}"
        )

        board = None
        valid_solution = False

        if model.SolCount > 0:
            candidate = []

            for r in range(n):
                cols = [
                    c for c in range(n)
                    if x[r, c].X > 0.5
                ]

                if len(cols) != 1:
                    candidate = None
                    break

                candidate.append(cols[0])

            if candidate is not None:
                board = candidate
                valid_solution = valid(board, n)

                if not valid_solution:
                    board = None

        status = _normalize_status(
            status,
            valid_solution,
            model.Status == GRB.INFEASIBLE,
        )

        return {
        "status": status,
        "board": board,
        "runtime_seconds": runtime,
        "valid_solution": valid_solution,
        "variables": n * n,
        "clauses": 0,
        "encoding_time": encoding_time,
        "solve_time": solve_time,
        }

    model.dispose()
    return result

SOLVERS = {
    "CPLEX_CP": solve_cplex_cp,
    "CPLEX_MIP": solve_cplex_mip,
    "GUROBI": solve_gurobi,
    "CPSAT": solve_cpsat,
}

SOLVER_MAX_SIZES = {
    "CPLEX_CP": 128,
    "CPLEX_MIP": 31,
    "GUROBI": 512,
}


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark N-Queens solvers"
    )
    parser.add_argument(
        "--solver",
        choices=[
            *SOLVERS, "all"
        ],
        default="all"
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        help="Board sizes to run, in the order provided (defaults to size.txt)"
    )
    args = parser.parse_args()
    sizes = args.sizes if args.sizes is not None else read_board_sizes()

    chosen = (
        SOLVERS if args.solver == "all"
        else {args.solver: SOLVERS[args.solver]}
    )
    rows = []
    existing_terminal_statuses = {
        name: read_terminal_statuses(name)
        for name in chosen
    }
    terminal_status_by_solver = {}

    for n in sizes:
        if n < 1:
            raise ValueError(f"Board size must be at least 1; received {n}")

        print(f"\nProcessing N={n}...", flush=True)

        for name, solver_func in chosen.items():
            terminal_status = terminal_status_by_solver.get(name)
            if terminal_status is None:
                terminal_status = existing_terminal_statuses[name].get(n)
                if terminal_status is not None:
                    terminal_status_by_solver[name] = terminal_status
                    continue

            if terminal_status is not None:
                row = {
                    "N": n,
                    "Encoding": name,
                    "Variables": "",
                    "Clauses": "",
                    "EncodingTime": "",
                    "SolveTime": "",
                    "TotalTime": "",
                    "Status": terminal_status,
                }
                rows.append(row)
                save_results(rows)
                print(row, flush=True)
                continue

            max_size = SOLVER_MAX_SIZES.get(name)
            if max_size is not None and n > max_size:
                row = {
                    "N": n,
                    "Encoding": name,
                    "Variables": "",
                    "Clauses": "",
                    "EncodingTime": "",
                    "SolveTime": "",
                    "TotalTime": "",
                    "Status": "SKIPPED",
                }
                rows.append(row)
                save_results(rows)
                print(row, flush=True)
                terminal_status_by_solver[name] = "SKIPPED"
                continue

            try:
                result, wall_time, timed_out = run_with_timeout(
                    solver_func,
                    (n,),
                )
                timed_out = timed_out or wall_time >= TIME_LIMIT_SECONDS
                if timed_out:
                    row = {
                        "N": n,
                        "Encoding": name,
                        "Variables": "",
                        "Clauses": "",
                        "EncodingTime": "",
                        "SolveTime": "",
                        "TotalTime": f"{TIME_LIMIT_SECONDS:.6f}",
                        "Status": f"TIMEOUT:{TIME_LIMIT_SECONDS}s",
                    }
                    rows.append(row)
                    save_results(rows)
                    print(row, flush=True)
                    terminal_status_by_solver[name] = row["Status"]
                    continue

                encoding_time = result.get("encoding_time")
                solve_time = result.get("solve_time")

                if solve_time is None:
                    solve_time = result["runtime_seconds"]

                if encoding_time is None:
                    encoding_time = 0.0

                total_time = wall_time
                status = result["status"]
                clauses = (
                    "" if status.startswith(("ERROR", "SKIPPED"))
                    else result.get("clauses", 0)
                )

                row = {
                    "N": n,
                    "Encoding": name,
                    "Variables": result.get("variables", ""),
                    "Clauses": clauses,
                    "EncodingTime": f"{encoding_time:.6f}",
                    "SolveTime": f"{solve_time:.6f}",
                    "TotalTime": f"{total_time:.6f}",
                    "Status": status,
                }
                rows.append(row)

                save_results(rows)
                print(row, flush=True)

            except Exception as error:
                row = {
                    "N": n,
                    "Encoding": name,
                    "Variables": "",
                    "Clauses": "",
                    "EncodingTime": "",
                    "SolveTime": "",
                    "TotalTime": "",
                    "Status": f"ERROR: {error}",
                }
                rows.append(row)
                save_results(rows)
                print(f"{name} ERROR: {error}", flush=True)

    results_path = save_results(rows)
    print(f"\nDa luu ket qua vao {results_path.name}")


if __name__ == "__main__":
    main()
