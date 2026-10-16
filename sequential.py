from pysat.solvers import Glucose3

from benchmark_utils import read_board_sizes, run_sat_benchmark

new_variables_count = 0


def generate_variables(n):
    return [[i * n + j + 1 for j in range(n)] for i in range(n)]


def generate_new_variables(n, start_index, length):
    start = n ** 2 + start_index
    return [i for i in range(start + 1, start + length)]


def at_most_one(clauses, variables, n):
    global new_variables_count
    if len(variables) < 2:
        return
    new_variables = generate_new_variables(n, new_variables_count, len(variables))
    new_variables_count += len(variables) - 1
    clauses.append([-variables[0], new_variables[0]])
    for i in range(1, len(variables) - 1):
        clauses.append([-variables[i], new_variables[i]])
        clauses.append([-new_variables[i - 1], new_variables[i]])
        clauses.append([-new_variables[i - 1], -variables[i]])
    clauses.append([-new_variables[len(variables) - 2], -variables[len(variables) - 1]])


def exactly_one(clauses, variables, n):
    clauses.append(variables)
    at_most_one(clauses, variables, n)


def generate_clauses(n, variables):
    clauses = []

    # Exactly one queen in each row
    for row in range(n):
        exactly_one(clauses, variables[row], n)

    # Exactly one queen in each column
    for col in range(n):
        exactly_one(clauses, [variables[row][col] for row in range(n)], n)

    # Horizontal reflection lets us restrict the first queen to the left half.
    clauses.append(variables[0][:(n + 1) // 2])

    # At most one queen in each diagonal
    for i in range(1, n):
        diagonal = []
        row = i
        col = 0
        while row >= 0 and col < n:
            diagonal.append(variables[row][col])
            row -= 1
            col += 1
        at_most_one(clauses, diagonal, n)

    for j in range(1, n - 1):
        diagonal = []
        row = n - 1
        col = j
        while row >= 0 and col < n:
            diagonal.append(variables[row][col])
            row -= 1
            col += 1
        at_most_one(clauses, diagonal, n)

    for i in range(n - 1):
        diagonal = []
        row = i
        col = 0
        while row < n and col < n:
            diagonal.append(variables[row][col])
            row += 1
            col += 1
        at_most_one(clauses, diagonal, n)

    for j in range(1, n - 1):
        diagonal = []
        row = 0
        col = j
        while row < n and col < n:
            diagonal.append(variables[row][col])
            row += 1
            col += 1
        at_most_one(clauses, diagonal, n)

    return clauses


def solve_n_queens(n):
    global new_variables_count
    new_variables_count = 0
    variables = generate_variables(n)
    clauses = generate_clauses(n, variables)

    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(clause)

    if solver.solve():
        model = solver.get_model()
        return [[int(model[i * n + j] > 0) for j in range(n)] for i in range(n)]
    return None


def print_solution(solution):
    if solution is None:
        print("No solution found.")
    else:
        for row in solution:
            print(" ".join("Q" if cell else "." for cell in row))


def main():
    run_sat_benchmark(
        "SAT-Sequential",
        read_board_sizes(),
        generate_variables,
        generate_clauses,
        reset_state=reset_encoding_state,
    )


def reset_encoding_state():
    global new_variables_count
    new_variables_count = 0


if __name__ == "__main__":
    main()