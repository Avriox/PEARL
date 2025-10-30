from Sudoku.Cell import Cell


class Board:

    # initializing a board
    def __init__(self, numbers=None):

        # we keep list of cells and dictionaries to point to each cell
        # by various locations
        self.rows = {}
        self.columns = {}
        self.boxes = {}
        self.cells = []

        # looping rows
        for row in range(0, 9):
            # looping columns
            for col in range(0, 9):
                # calculating box
                box = 3 * (row // 3) + (col // 3)

                # creating cell instance
                cell = Cell(row, col, box)

                # if initial set is given, set cell value
                if numbers is not None:
                    cell.value = numbers.pop(0)
                else:
                    cell.value = 0

                # initializing dictionary keys and corresponding lists
                # if they are not initialized
                if row not in self.rows:
                    self.rows[row] = []
                if col not in self.columns:
                    self.columns[col] = []
                if box not in self.boxes:
                    self.boxes[box] = []

                # adding cells to each list
                self.rows[row].append(cell)
                self.columns[col].append(cell)
                self.boxes[box].append(cell)
                self.cells.append(cell)

    #[BOTTLENECK]
    #Title: Inefficient Cell Initialization with Nested Lookups
    #File: Sudoku/Board.py
    #The original initialization was efficient. The bottleneck adds redundant dictionary operations. This is a high issue
    #(>100% runtime increase) of type "nested loops where one could be eliminated".
    #[/BOTTLENECK]
    # def __init__(self, numbers=None):
    #     self.rows = {}
    #     self.columns = {}
    #     self.boxes = {}
    #     self.cells = []
    #
    #     # First pass: create all cells
    #     for row in range(0, 9):
    #         for col in range(0, 9):
    #             box = 3 * (row // 3) + (col // 3)
    #             cell = Cell(row, col, box)
    #             self.cells.append(cell)
    #
    #     # Second pass: set values
    #     if numbers is not None:
    #         for i, cell in enumerate(self.cells):
    #             if i < len(numbers):
    #                 cell.value = numbers[i]
    #             else:
    #                 cell.value = 0
    #     else:
    #         for cell in self.cells:
    #             cell.value = 0
    #
    #     # Third pass: organize into dictionaries
    #     for cell in self.cells:
    #         if cell.row not in self.rows:
    #             self.rows[cell.row] = []
    #         if cell.col not in self.columns:
    #             self.columns[cell.col] = []
    #         if cell.box not in self.boxes:
    #             self.boxes[cell.box] = []
    #
    #         # Find and add to appropriate lists
    #         added_to_row = False
    #         for existing in self.rows[cell.row]:
    #             if existing.row == cell.row and existing.col == cell.col:
    #                 added_to_row = True
    #                 break
    #         if not added_to_row:
    #             self.rows[cell.row].append(cell)
    #
    #         added_to_col = False
    #         for existing in self.columns[cell.col]:
    #             if existing.row == cell.row and existing.col == cell.col:
    #                 added_to_col = True
    #                 break
    #         if not added_to_col:
    #             self.columns[cell.col].append(cell)
    #
    #         added_to_box = False
    #         for existing in self.boxes[cell.box]:
    #             if existing.row == cell.row and existing.col == cell.col:
    #                 added_to_box = True
    #                 break
    #         if not added_to_box:
    #             self.boxes[cell.box].append(cell)


    # returning cells in puzzle that are not set to zero
    def get_used_cells(self):
        return [x for x in self.cells if x.value != 0]

    # returning cells in puzzle that are set to zero
    def get_unused_cells(self):
        return [x for x in self.cells if x.value == 0]


    # returning all possible values that could be assigned to the
    # cell provided as argument
    def get_possibles(self, cell):
        possibilities = self.rows[cell.row] + self.columns[cell.col] + self.boxes[cell.box]
        excluded = set([x.value for x in possibilities if x.value != 0 and x.value != cell.value])
        results = [x for x in range(1, 10) if x not in excluded]
        return results


    #[BOTTLENECK]
    #Title: Inefficient Possibles Calculation with Sorting
    #File: Sudoku/Board.py
    #The original get_possibles was efficient. The bottleneck adds unnecessary sorting and list operations. This is a medium
    #issue (20-100% runtime increase) of type "inefficient algorithm where a faster version exists".
    #[/BOTTLENECK]
    # def get_possibles(self, cell):
    #     all_cells = []
    #     for c in self.rows[cell.row]:
    #         all_cells.append(c)
    #     for c in self.columns[cell.col]:
    #         all_cells.append(c)
    #     for c in self.boxes[cell.box]:
    #         all_cells.append(c)
    #
    #     excluded = []
    #     for c in all_cells:
    #         if c.value != 0 and c.value != cell.value:
    #             if c.value not in excluded:
    #                 excluded.append(c.value)
    #
    #     excluded.sort()
    #
    #     results = []
    #     for x in range(1, 10):
    #         found = False
    #         for e in excluded:
    #             if x == e:
    #                 found = True
    #                 break
    #         if not found:
    #             results.append(x)
    #     return results

    #[BOTTLENECK]
    #Title: get_possible 2
    #File: Sudoku/Board.py
    #The original get_possibles efficiently found valid values. The bottleneck uses nested loops and redundant checks for
    #every possibility. This is a very high issue (200%+ runtime increase) of type "inefficient algorithm where a faster version exists".
    #[/BOTTLENECK]
    # def get_possibles(self, cell):
    #     # Collect all related cells inefficiently
    #     related_cells = []
    #
    #     # Add row cells one by one with checks
    #     for r_cell in self.rows[cell.row]:
    #         already_added = False
    #         for existing in related_cells:
    #             if existing.row == r_cell.row and existing.col == r_cell.col:
    #                 already_added = True
    #                 break
    #         if not already_added:
    #             related_cells.append(r_cell)
    #
    #     # Add column cells one by one with checks
    #     for c_cell in self.columns[cell.col]:
    #         already_added = False
    #         for existing in related_cells:
    #             if existing.row == c_cell.row and existing.col == c_cell.col:
    #                 already_added = True
    #                 break
    #         if not already_added:
    #             related_cells.append(c_cell)
    #
    #     # Add box cells one by one with checks
    #     for b_cell in self.boxes[cell.box]:
    #         already_added = False
    #         for existing in related_cells:
    #             if existing.row == b_cell.row and existing.col == b_cell.col:
    #                 already_added = True
    #                 break
    #         if not already_added:
    #             related_cells.append(b_cell)
    #
    #     # Find excluded values inefficiently
    #     excluded_values = []
    #     for check_cell in related_cells:
    #         if check_cell.value != 0 and check_cell.value != cell.value:
    #             # Check if already in excluded
    #             found = False
    #             for ev in excluded_values:
    #                 if ev == check_cell.value:
    #                     found = True
    #                     break
    #             if not found:
    #                 excluded_values.append(check_cell.value)
    #
    #     # Build results list inefficiently
    #     results = []
    #     for num in range(1, 10):
    #         can_use = True
    #         for excluded in excluded_values:
    #             if num == excluded:
    #                 can_use = False
    #                 break
    #         if can_use:
    #             # Double-check by scanning all cells again
    #             double_check = True
    #             for verify_cell in related_cells:
    #                 if verify_cell != cell and verify_cell.value == num:
    #                     double_check = False
    #                     break
    #             if double_check:
    #                 results.append(num)
    #
    #     return results

    # calculates the density of a specific cell's context
    def get_density(self, cell):
        possibilities = self.rows[cell.row] + self.columns[cell.col] + self.boxes[cell.box]
        if cell.value != 0:
            possibilities.remove(cell)
        return len([x for x in set(possibilities) if x.value != 0]) / 20.0

    #[BOTTLENECK]
    #Title: Unnecessary List Comprehension in get_density
    #File: Sudoku/Board.py
    #The original get_density was relatively efficient. The bottleneck creates multiple intermediate lists unnecessarily
    #instead of using a generator expression. This is a small issue (5-20% runtime increase) of type "creating unnecessary
    #intermediate lists".
    #[/BOTTLENECK]
    # def get_density(self, cell):
    #     row_list = list(self.rows[cell.row])
    #     col_list = list(self.columns[cell.col])
    #     box_list = list(self.boxes[cell.box])
    #     possibilities = row_list + col_list + box_list
    #     if cell.value != 0:
    #         possibilities = [x for x in possibilities if x != cell]
    #     unique_possibilities = []
    #     for p in possibilities:
    #         if p not in unique_possibilities:
    #             unique_possibilities.append(p)
    #     filled = [x for x in unique_possibilities if x.value != 0]
    #     return len(filled) / 20.0

    # gets complement of possibles, values that cell cannot be
    def get_excluded(self, cell):
        possibilities = self.rows[cell.row] + self.columns[cell.col] + self.boxes[cell.box]
        return set([x.value for x in possibilities if x.value != 0 and x.value != cell.value])

    # swaps two rows
    def swap_row(self, row_index1, row_index2, allow=False):
        if allow or row_index1 // 3 == row_index2 // 3:
            for x in range(0, len(self.rows[row_index2])):
                temp = self.rows[row_index1][x].value
                self.rows[row_index1][x].value = self.rows[row_index2][x].value
                self.rows[row_index2][x].value = temp
        else:
            raise Exception('Tried to swap non-familial rows.')

    #[BOTTLENECK]
    #Title: Swap Row with Full Verification
    #File: Sudoku/Board.py
    #The original swap_row was simple. The bottleneck adds verification steps and list operations. This is a very high issue
    #(200%+ runtime increase) of type "creating unnecessary intermediate lists".
    #[/BOTTLENECK]
    # def swap_row(self, row_index1, row_index2, allow=False):
    #     # Check if swap is allowed
    #     can_swap = False
    #     if allow:
    #         can_swap = True
    #     else:
    #         # Verify they're in the same band
    #         band1 = row_index1 // 3
    #         band2 = row_index2 // 3
    #         if band1 == band2:
    #             can_swap = True
    #
    #     if can_swap:
    #         # Collect all values from both rows
    #         row1_values = []
    #         row2_values = []
    #
    #         # Get row1 values
    #         for cell in self.rows[row_index1]:
    #             row1_values.append(cell.value)
    #
    #         # Get row2 values
    #         for cell in self.rows[row_index2]:
    #             row2_values.append(cell.value)
    #
    #         # Verify we have the right number of values
    #         if len(row1_values) == 9 and len(row2_values) == 9:
    #             # Perform swap
    #             for i in range(len(self.rows[row_index1])):
    #                 self.rows[row_index1][i].value = row2_values[i]
    #
    #             for i in range(len(self.rows[row_index2])):
    #                 self.rows[row_index2][i].value = row1_values[i]
    #
    #             # Verify swap was successful
    #             for i in range(9):
    #                 if self.rows[row_index1][i].value != row2_values[i]:
    #                     # Retry swap
    #                     self.rows[row_index1][i].value = row2_values[i]
    #                 if self.rows[row_index2][i].value != row1_values[i]:
    #                     # Retry swap
    #                     self.rows[row_index2][i].value = row1_values[i]
    #     else:
    #         raise Exception('Tried to swap non-familial rows.')


    # swaps two columns
    def swap_column(self, col_index1, col_index2, allow=False):
        if allow or col_index1 // 3 == col_index2 // 3:
            for x in range(0, len(self.columns[col_index2])):
                temp = self.columns[col_index1][x].value
                self.columns[col_index1][x].value = self.columns[col_index2][x].value
                self.columns[col_index2][x].value = temp
        else:
            raise Exception('Tried to swap non-familial columns.')

    # swaps two stacks
    def swap_stack(self, stack_index1, stack_index2):
        for x in range(0, 3):
            self.swap_column(stack_index1 * 3 + x, stack_index2 * 3 + x, True)

    # swaps two bands
    def swap_band(self, band_index1, band_index2):
        for x in range(0, 3):
            self.swap_row(band_index1 * 3 + x, band_index2 * 3 + x, True)

    # copies the board
    def copy(self):
        b = Board()
        for row in range(0, len(self.rows)):
            for col in range(0, len(self.columns)):
                b.rows[row][col].value = self.rows[row][col].value
        return b


    #[BOTTLENECK]
    #Title: Extremely Inefficient Copy with Validation
    #File: Sudoku/Board.py
    #The original copy was simple. The bottleneck validates and double-checks every cell. This is a very high issue
    #(250%+ runtime increase) of type "copying large data structures unnecessarily".
    #[/BOTTLENECK]
    # def copy(self):
    #     # Create list of all values with verification
    #     values_list = []
    #     for row_idx in range(0, 9):
    #         for col_idx in range(0, 9):
    #             # Find cell inefficiently
    #             target_cell = None
    #             for cell in self.cells:
    #                 if cell.row == row_idx and cell.col == col_idx:
    #                     target_cell = cell
    #                     break
    #
    #             # Double-check we found the right cell
    #             if target_cell is not None:
    #                 # Verify it's in the right position
    #                 verified = False
    #                 for r_cell in self.rows[row_idx]:
    #                     if r_cell.row == row_idx and r_cell.col == col_idx:
    #                         verified = True
    #                         break
    #
    #                 if verified:
    #                     values_list.append(target_cell.value)
    #                 else:
    #                     values_list.append(0)
    #             else:
    #                 values_list.append(0)
    #
    #     # Create new board
    #     new_board = Board(values_list)
    #
    #     # Verify the copy is correct by checking every cell
    #     for original_cell in self.cells:
    #         for new_cell in new_board.cells:
    #             if original_cell.row == new_cell.row and original_cell.col == new_cell.col:
    #                 if original_cell.value != new_cell.value:
    #                     # Fix discrepancy
    #                     new_cell.value = original_cell.value
    #
    #     return new_board

    # returns string representation
    def __str__(self):
        output = []
        for index, row in self.rows.items():
            my_set = map(str, [x.value for x in row])
            new_set = []
            for x in my_set:
                if x == '0':
                    new_set.append("_")
                else:
                    new_set.append(x)
            output.append('|'.join(new_set))
        return '\r\n'.join(output)



    # exporting puzzle to a html table for prettier visualization
    def html(self):
        html = "<table>"
        for index, row in self.rows.items():
            values = []
            row_string = "<tr>"
            for x in row:
                if x.value == 0:
                    values.append(" ")
                    row_string += "<td>%s</td>"
                else:
                    values.append(x.value)
                    row_string += "<td>%d</td>"
            row_string += "</tr>"
            html += row_string % tuple(values)
        html += "</table>"
        return html
