import csv
import time
from pathlib import Path

from pysat.solvers import Glucose3


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


def run_sat_benchmark(encoding, sizes, generate_variables, generate_clauses,
                      reset_state=None, output_path=None):
    rows = []
    for n in sizes:
        if n < 1:
            raise ValueError(f"Board size must be at least 1; received {n}")
        if reset_state:
            reset_state()

        print(f"\nProcessing N={n}...", flush=True)
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

        rows.append({
            "N": n,
            "Encoding": encoding,
            "Variables": max(n * n, max_variable),
            "Clauses": len(clauses),
            "EncodingTime": f"{encoding_time:.3f}",
            "SolveTime": f"{solve_time:.3f}",
            "TotalTime": f"{encoding_time + solve_time:.3f}",
            "Status": "SAT" if is_satisfiable else "UNSAT",
        })
        results_path = save_results(rows, output_path)
        _print_table(rows)
        print(f"Results saved to {results_path}", flush=True)

    return rows
