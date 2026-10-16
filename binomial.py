from pysat.solvers import Glucose3

from benchmark_utils import read_board_sizes, run_sat_benchmark


def generate_variables(n):
    return [[i * n + j + 1 for j in range(n)] for i in range(n)]


def at_most_one(clauses, variables, next_auxiliary_variable):
    if len(variables) < 2:
        return next_auxiliary_variable

    auxiliary_variables = list(
        range(next_auxiliary_variable, next_auxiliary_variable + len(variables) - 1)
    )
    clauses.append([-variables[0], auxiliary_variables[0]])
    for i in range(1, len(variables) - 1):
        clauses.append([-variables[i], auxiliary_variables[i]])
        clauses.append([-auxiliary_variables[i - 1], auxiliary_variables[i]])
        clauses.append([-variables[i], -auxiliary_variables[i - 1]])
    clauses.append([-variables[-1], -auxiliary_variables[-1]])
    return next_auxiliary_variable + len(auxiliary_variables)


def exactly_one(clauses, variables, next_auxiliary_variable):
    clauses.append(variables)
    return at_most_one(clauses, variables, next_auxiliary_variable)


def generate_clauses(n, variables):
    clauses = []
    next_auxiliary_variable = n * n + 1

    # Exactly one queen in each row
    for i in range(n):
        next_auxiliary_variable = exactly_one(
            clauses, variables[i], next_auxiliary_variable
        )

    # Exactly one queen in each column
    for j in range(n):
        next_auxiliary_variable = exactly_one(
            clauses,
            [variables[i][j] for i in range(n)],
            next_auxiliary_variable,
        )


    # At most one queen in each diagonal
    for start_col in range(n):
        diagonal = []
        row, col = 0, start_col
        while row < n and col < n:
            diagonal.append(variables[row][col])
            row += 1
            col += 1
        next_auxiliary_variable = at_most_one(
            clauses, diagonal, next_auxiliary_variable
        )

    for start_row in range(1, n):
        diagonal = []
        row, col = start_row, 0
        while row < n and col < n:
            diagonal.append(variables[row][col])
            row += 1
            col += 1
        next_auxiliary_variable = at_most_one(
            clauses, diagonal, next_auxiliary_variable
        )

    for start_col in range(n):
        diagonal = []
        row, col = 0, start_col
        while row < n and col >= 0:
            diagonal.append(variables[row][col])
            row += 1
            col -= 1
        next_auxiliary_variable = at_most_one(
            clauses, diagonal, next_auxiliary_variable
        )

    for start_row in range(1, n):
        diagonal = []
        row, col = start_row, n - 1
        while row < n and col >= 0:
            diagonal.append(variables[row][col])
            row += 1
            col -= 1
        next_auxiliary_variable = at_most_one(
            clauses, diagonal, next_auxiliary_variable
        )

    return clauses


def solve_n_queens(n):
    variables = generate_variables(n)
    clauses = generate_clauses(n, variables)

    solver = Glucose3()
    for clause in clauses:
        solver.add_clause(clause)

    if solver.solve():
        model = solver.get_model()
        return [[int(model[i * n + j] > 0) for j in range(n)] for i in range(n)]
    else:
        return None


def print_solution(solution):
    if solution is None:
        print("No solution found.")
    else:
        print(solution)
        for row in solution:
            print(" ".join("Q" if cell else "." for cell in row))

if __name__ == "__main__":
    run_sat_benchmark(
        "SAT-Binomial",
        read_board_sizes(),
        generate_variables,
        generate_clauses,
    )
