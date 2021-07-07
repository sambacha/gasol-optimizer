#!/usr/bin/env python3

from superoptimization_enconding import generate_smtlib_encoding, generate_smtlib_encoding_appending
from utils_bckend import add_bars_and_index_to_string
import json
import argparse
from encoding_files import initialize_dir_and_streams, write_encoding
from smtlib_utils import set_logic, check_sat
import re
from encoding_utils import generate_disasm_map, generate_costs_ordered_dict, generate_stack_theta, generate_instr_map, \
    generate_uninterpreted_theta
import copy

costabs_path = "/tmp/gasol/"


def parse_data(json_path, var_initial_idx=0, with_simplifications=True):
    # We can pass either the path to a json file, or
    # directly the dict that contains the SFS.
    if type(json_path) == str:
        with open(json_path) as path:
            data = json.load(path)
    else:
        data = json_path

    bs = data['max_sk_sz']

    # If simplifications have been applied, then we retrieve field "user_instrs". Otherwise,
    # field "non_inter" is retrieved.
    if with_simplifications:
        user_instr = data['user_instrs']

        # Note that b0 can be either max_progr_len
        # or init_progr_len
        # b0 = data['max_progr_len']
        b0 = data['init_progr_len']

    else:
        user_instr = data['init_info']['non_inter']
        # If no simplifications were made, we take the max_progr_len instead to ensure there is
        # no problem with index.
        b0 = data['max_progr_len']

    # To avoid errors, we copy user instr to generate a new one
    new_user_instr = []

    for instr in user_instr:
        new_instr = copy.deepcopy(instr)
        new_instr['outpt_sk'] = list(map(lambda x: add_bars_and_index_to_string(x, var_initial_idx), instr['outpt_sk']))
        new_instr['inpt_sk'] = list(map(lambda x: add_bars_and_index_to_string(x, var_initial_idx), instr['inpt_sk']))

        if len(list(filter(lambda x: x == "|s(2676)|", new_instr['outpt_sk']))) > 0:
            print(instr, new_instr, data['vars'])

        new_user_instr.append(new_instr)

    initial_stack = list(map(lambda x: add_bars_and_index_to_string(x, var_initial_idx), data['src_ws']))
    final_stack = list(map(lambda x: add_bars_and_index_to_string(x, var_initial_idx), data['tgt_ws']))
    variables = list(map(lambda x: add_bars_and_index_to_string(x, var_initial_idx), data['vars']))

    current_cost = data['current_cost']
    instr_seq = data.get('disasm_seq', [])
    return b0, bs, new_user_instr, variables, initial_stack, final_stack, current_cost, instr_seq


def initialize_flags_and_additional_info(args_i, current_cost, instr_seq, previous_solution_dict):
    if args_i is None:
        flags = {'at-most': False, 'pushed-at-least': False,
                 'instruction-order': False,
                 'no-output-before-pop': False, 'inequality-gas-model': False,
                 'initial-solution': False, 'default-encoding': False,
                 'number-instruction-gas-model': False}
        additional_info = {'tout': 10, 'solver': "oms", 'current_cost': current_cost,
                           'instr_seq': instr_seq, 'previous_solution': previous_solution_dict}
    else:
        flags = {'at-most': args_i.at_most, 'pushed-at-least': args_i.pushed_once,
                 'instruction-order': args_i.instruction_order,
                 'no-output-before-pop': args_i.no_output_before_pop,
                 'inequality-gas-model': args_i.inequality_gas_model,
                 'initial-solution': args_i.initial_solution, 'default-encoding': args_i.default_encoding,
                 'number-instruction-gas-model': args_i.number_instruction_gas_model}
        additional_info = {'tout': args_i.tout, 'solver': args_i.solver, 'current_cost': current_cost,
                           'instr_seq': instr_seq, 'previous_solution': previous_solution_dict}
    return flags, additional_info


# Executes the smt encoding generator from the main script
def execute_syrup_backend(args_i,json_file = None, previous_solution_dict = None, block_name = None, timeout=10):
    path = costabs_path
    # Args_i is None if the function is called from syrup-asm. In this case
    # we assume by default oms, and json_file already contains the sfs dict
    if args_i is None:
        es = initialize_dir_and_streams(path,"oms", block_name)
        json_path = json_file
    else:
        if json_file:
            json_path = json_file
        else:
            json_path = args_i.source

        path = costabs_path
        solver = args_i.solver
        es = initialize_dir_and_streams(path, solver, json_path)

    b0, bs, user_instr, variables, initial_stack, final_stack, current_cost, instr_seq = parse_data(json_path)

    flags, additional_info = initialize_flags_and_additional_info(args_i, current_cost, instr_seq, previous_solution_dict)

    additional_info['tout'] = timeout

    generate_smtlib_encoding(b0, bs, user_instr, variables, initial_stack, final_stack, flags, additional_info)

    es.close()


def execute_syrup_backend_combined(sfs_dict, instr_sequence_dict, block_optimized_dict, contract_name, solver):
    next_empty_idx = 0
    # Stores the number of previous stack variables to ensures there's no collision
    next_var_idx = 0

    es = initialize_dir_and_streams(costabs_path, solver, contract_name)

    write_encoding(set_logic('QF_LIA'))

    for block in sfs_dict:

        sfs_block = sfs_dict[block]

        log_dict = instr_sequence_dict[block]
        is_optimized = block_optimized_dict[block]

        print(block)

        b0, bs, user_instr, variables, initial_stack, final_stack, current_cost, instr_seq = parse_data(sfs_block,
                                                                                                        next_var_idx,
                                                                                                        is_optimized)
        generate_smtlib_encoding_appending(b0, bs, user_instr, variables, initial_stack, final_stack,
                                           log_dict, next_empty_idx)
        next_empty_idx += b0 + 1

        # Next available index for assigning var values is equal to the maximum of previous ones
        if variables:
            next_var_idx = max(map(lambda x: int(re.search('\d+', x).group()), variables)) + 1

    write_encoding(check_sat())
    es.close()


# Given the max stack size (bs) and the user instructions directly from the json, generates four dicts:
# one for the conversion of an opcode id to the corresponding theta value, other for the disasm associated
# to the theta value, another for the bytecode associated to the theta value, and finally, the cost of each
# opcode associated to a theta value.
def generate_theta_dict_from_sequence(bs, usr_instr):
    theta_stack = generate_stack_theta(bs)
    theta_comm, theta_non_comm = generate_uninterpreted_theta(usr_instr, len(theta_stack))
    theta_dict = dict(theta_stack, **theta_comm, **theta_non_comm)
    instr_map = generate_instr_map(usr_instr, theta_stack, theta_comm, theta_non_comm)
    disasm_map = generate_disasm_map(usr_instr, theta_dict)
    costs_map = generate_costs_ordered_dict(bs, usr_instr, theta_dict)
    return theta_dict, instr_map, disasm_map, costs_map


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description='Backend of syrup tool')
    ap.add_argument('json_path', help='Path to json file that contains the SFS')
    ap.add_argument('-out', help='Path to dir where the smt is stored (by default, in ' + str(costabs_path) + ")",
                    nargs='?', default=costabs_path, metavar='dir')
    ap.add_argument('-write-only', help='print smt constraint in SMT-LIB format, '
                                                             'a mapping to instructions, and objectives',
                    action='store_true', dest='write_only')
    ap.add_argument('-at-most', help='add a constraint for each uninterpreted function so that they are used at most once',
                    action='store_true', dest='at_most')
    ap.add_argument('-pushed-once', help='add a constraint to indicate that each pushed value is pushed at least once',
                    action='store_true', dest='pushed_once')
    ap.add_argument("-solver", "--solver", help="Choose the solver", choices = ["z3","barcelogic","oms"], default="z3")
    ap.add_argument("-instruction-order", help='add a constraint representing the order among instructions',
                    action='store_true', dest='instruction_order')
    ap.add_argument("-no-output-before-pop", help='Add a constraint representing the fact that the previous instruction'
                                                  'of a pop can only be a instruction that does not produce an element',
                    action='store_true', dest='no_output_before_pop')
    ap.add_argument("-tout", metavar='timeout', action='store', type=int, help="Timeout in seconds. "
                                                                               "Works only for z3 and oms (so far)")
    ap.add_argument("-inequality-gas-model", dest='inequality_gas_model', action='store_true',
                    help="Soft constraints with inequalities instead of equalities")
    ap.add_argument("-initial-solution", dest='initial_solution', action='store_true',
                    help="Consider the instructions of blocks without optimizing as part of the encoding")
    ap.add_argument("-disable-default-encoding", dest='default_encoding', action='store_false',
                    help="Disable the constraints added for the default encoding")
    ap.add_argument("-number-instruction-gas-model", dest='number_instruction_gas_model', action='store_true',
                    help="Soft constraints for optimizing the number of instructions instead of gas")
    ap.add_argument("-check-log-file", dest='log_path', action='store', metavar="log_file",
                        help="Checks every solution from a log file generated by -generate-log-file is "
                             "returned by the solver")

    args = vars(ap.parse_args())
    json_path = args['json_path']
    path = args['out']
    solver = args['solver']
    timeout = args['tout']

    b0, bs, user_instr, variables, initial_stack, final_stack, current_cost, instr_seq = parse_data(json_path)

    flags = {'at-most': args['at_most'], 'pushed-at-least': args['pushed_once'],
             'instruction-order': args['instruction_order'], 'no-output-before-pop': args['no_output_before_pop'],
             'inequality-gas-model': args['inequality_gas_model'], 'initial-solution': args['initial_solution'],
             'default-encoding': args['default_encoding'],
             'number-instruction-gas-model': args['number_instruction_gas_model']}

    log_dict = None
    if args['log_path'] is not None:
        with open(args['log_path'], 'r') as log_path:
            log_dict = json.load(log_path)
    additional_info = {'tout': args['tout'], 'solver': solver, 'current_cost': current_cost, 'instr_seq': instr_seq,
                       'previous_solution': log_dict}
    es = initialize_dir_and_streams(path, solver)

    generate_smtlib_encoding(b0, bs, user_instr, variables, initial_stack, final_stack, flags, additional_info)

    es.close()