import csv
import multiprocessing
import time
import traceback
from pathlib import Path

from pysat.solvers import Glucose3


TIME_LIMIT_SECONDS = 60

RESULT_COLUMNS = [
    "N",
    "Encoding",
    "Variables",
    "Clauses",
    "EncodingTime",
    "SolveTime",
    "TotalTime",
    "Status",
]


def _run_with_result_sender(connection, target, args):
    try:
        connection.send(("result", target(*args)))
    except BaseException:
        connection.send(("error", traceback.format_exc()))
    finally:
        connection.close()


def run_with_timeout(target, args, timeout_seconds=TIME_LIMIT_SECONDS):
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_run_with_result_sender,
        args=(child_connection, target, args),
    )
    started = time.perf_counter()
    process.start()
    child_connection.close()
    remaining = max(0.0, timeout_seconds - (time.perf_counter() - started))
    process.join(remaining)

    if process.is_alive():
        process.terminate()
        process.join()
        elapsed = time.perf_counter() - started
        parent_connection.close()
        return None, elapsed, True

    if not parent_connection.poll():
        parent_connection.close()
        raise RuntimeError(
            f"Benchmark worker exited without a result (exit code {process.exitcode})"
        )

    result_type, payload = parent_connection.recv()
    parent_connection.close()
    elapsed = time.perf_counter() - started
    if elapsed >= timeout_seconds:
        return None, elapsed, True
    if result_type == "error":
        raise RuntimeError(f"Benchmark worker failed:\n{payload}")
    return payload, elapsed, False


def read_board_sizes(path=None):
    sizes_path = Path(path) if path else Path(__file__).with_name("size.txt")
    try:
        lines = sizes_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError(f"Cannot read board sizes from {sizes_path}: {error}") from error

    sizes = []
    for line_number, line in enumerate(lines, start=1):
        value = line.strip()
        if not value:
            continue
        try:
            size = int(value)
        except ValueError as error:
            raise ValueError(
                f"Invalid board size on line {line_number} of {sizes_path}: {value!r}"
            ) from error
        if size < 1:
            raise ValueError(
                f"Board size on line {line_number} of {sizes_path} must be at least 1"
            )
        sizes.append(size)

    if not sizes:
        raise ValueError(f"No board sizes found in {sizes_path}")
    return sizes


def read_terminal_statuses(encoding, output_path=None):
    results_path = Path(output_path) if output_path else Path(__file__).with_name("results.csv")
    if not results_path.exists():
        return {}

    terminal_statuses = {}
    with results_path.open("r", newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if row.get("Encoding") != encoding:
                continue

            status = (row.get("Status") or "").strip()
            if status == "SKIPPED" or status.startswith("SKIPPED:"):
                normalized_status = "SKIPPED"
            elif status == "TIMEOUT" or status.startswith("TIMEOUT:"):
                normalized_status = f"TIMEOUT:{TIME_LIMIT_SECONDS}s"
            else:
                continue

            try:
                size = int(row["N"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid board size in {results_path} for {encoding}: {row.get('N')!r}"
                ) from error
            terminal_statuses[size] = normalized_status

    return terminal_statuses


def save_results(rows, output_path=None):
    results_path = Path(output_path) if output_path else Path(__file__).with_name("results.csv")
    existing_rows = []
    if results_path.exists():
        with results_path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            new_keys = {(int(row["N"]), row["Encoding"]) for row in rows}
            existing_rows = [
                {column: row.get(column, "") for column in RESULT_COLUMNS}
                for row in reader
                if (int(row["N"]), row["Encoding"]) not in new_keys
            ]

    all_rows = existing_rows + rows
    all_rows.sort(key=lambda row: (int(row["N"]), row["Encoding"]))
    with results_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
    return results_path


def _print_table(rows):
    widths = {
        column: max(
            len(column),
            *(len(str(row[column])) for row in rows),
        )
        for column in RESULT_COLUMNS
    }
    print(" | ".join(column.ljust(widths[column]) for column in RESULT_COLUMNS))
    print("-+-".join("-" * widths[column] for column in RESULT_COLUMNS))
    for row in rows:
        print(" | ".join(str(row[column]).ljust(widths[column]) for column in RESULT_COLUMNS))


def _run_sat_instance(n, generate_variables, generate_clauses, reset_state):
    if reset_state:
        reset_state()

    encoding_start = time.perf_counter()
    variables = generate_variables(n)
    clauses = generate_clauses(n, variables)
    encoding_time = time.perf_counter() - encoding_start

    max_variable = max(
        (abs(literal) for clause in clauses for literal in clause),
        default=n * n,
    )
    solver = Glucose3()
    solve_start = time.perf_counter()
    try:
        for clause in clauses:
            solver.add_clause(clause)
        is_satisfiable = solver.solve()
    finally:
        solver.delete()
    solve_time = time.perf_counter() - solve_start

    return {
        "variables": max(n * n, max_variable),
        "clauses": len(clauses),
        "encoding_time": encoding_time,
        "solve_time": solve_time,
        "satisfiable": is_satisfiable,
    }


def run_sat_benchmark(encoding, sizes, generate_variables, generate_clauses,
                      reset_state=None, output_path=None):
    rows = []
    terminal_statuses = read_terminal_statuses(encoding, output_path)
    terminal_status = None
    for n in sizes:
        if n < 1:
            raise ValueError(f"Board size must be at least 1; received {n}")

        print(f"\nProcessing N={n}...", flush=True)
        if terminal_status is None and n in terminal_statuses:
            terminal_status = terminal_statuses[n]
            continue

        if terminal_status is not None:
            row = {
                "N": n,
                "Encoding": encoding,
                "Variables": "",
                "Clauses": "",
                "EncodingTime": "",
                "SolveTime": "",
                "TotalTime": "",
                "Status": terminal_status,
            }
            rows.append(row)
            results_path = save_results(rows, output_path)
            _print_table(rows)
            print(f"Results saved to {results_path}", flush=True)
            continue

        result, total_time, timed_out = run_with_timeout(
            _run_sat_instance,
            (n, generate_variables, generate_clauses, reset_state),
        )
        timed_out = timed_out or total_time >= TIME_LIMIT_SECONDS
        if timed_out:
            row = {
                "N": n,
                "Encoding": encoding,
                "Variables": "",
                "Clauses": "",
                "EncodingTime": "",
                "SolveTime": "",
                "TotalTime": f"{TIME_LIMIT_SECONDS:.3f}",
                "Status": f"TIMEOUT:{TIME_LIMIT_SECONDS}s",
            }
            terminal_status = row["Status"]
        else:
            row = {
                "N": n,
                "Encoding": encoding,
                "Variables": result["variables"],
                "Clauses": result["clauses"],
                "EncodingTime": f'{result["encoding_time"]:.3f}',
                "SolveTime": f'{result["solve_time"]:.3f}',
                "TotalTime": f"{total_time:.3f}",
                "Status": "SAT" if result["satisfiable"] else "UNSAT",
            }
        rows.append(row)
        results_path = save_results(rows, output_path)
        _print_table(rows)
        print(f"Results saved to {results_path}", flush=True)

    return rows
