import json
import math
from timeit import default_timer as dtimer
from sfs_generator.utils import is_integer,all_integers, find_sublist
import  sfs_generator.opcodes as opcodes
import os
from global_params.paths import gasol_path, json_path


terminate_block = ["ASSERTFAIL","RETURN","REVERT","SUICIDE","STOP"]

global split_block
split_block = ["LOG0","LOG1","LOG2","LOG3","LOG4","CALLDATACOPY","CODECOPY","EXTCODECOPY","RETURNDATACOPY","MSTORE8","CALL","STATICCALL","DELEGATECALL","CREATE","CREATE2","ASSIGNIMMUTABLE"]

pre_defined_functions = ["PUSH","POP","SWAP","DUP"]

zero_ary = ["origin","caller","callvalue","address","number","gasprice","difficulty","coinbase","timestamp","codesize","gaslimit","gas","calldatasize","returndatasize","msize","selfbalance","chainid","pushdeployaddress","pushsize"]

commutative_bytecodes = ["ADD","MUL","EQ","AND","OR","XOR"]

global original_opcodes
original_opcodes = []

global gas_t
gas_t = 0

global compute_gast
compute_gast = True

global int_not0
int_not0 = []

global source_name
source_name = ""

global cname
cname = ""

global saved_push
saved_push = 0

global gas_saved_op
gas_saved_op = 0

global blocks_json_dict
blocks_json_dict = {}

global sfs_contracts
sfs_contracts = {}

global split_sto
split_sto = False


def init_globals():
    
    global u_counter
    u_counter = 0

    global u_dict
    u_dict = {}
    
    global s_counter
    s_counter = 0

    global s_dict
    s_dict = {}

    global variable_content
    variable_content = {}
    
    global user_defins
    user_defins = []

    global user_def_counter
    user_def_counter = {}

    global already_defined_userdef
    already_defined_userdef = []
    
    global max_instr_size
    max_instr_size = 0

    global max_stack_size
    max_stack_size = 0

    global num_pops
    num_pops = 0

    global discount_op
    discount_op = 0

    global already_considered
    already_considered = []
    
def add_storage2split():
    global split_block
    global split_sto

    split_sto = True
    split_block+=["SSTORE","MSTORE"]
    
def filter_opcodes(rule):
    instructions = rule.get_instructions()
    rbr_ins_aux = list(filter(lambda x: x.find("nop(")==-1, instructions))
    rbr_ins = list(filter(lambda x: x!="" and x.find("skip")==-1, rbr_ins_aux))
    return rbr_ins

def get_opcodes(rule):
    instructions = rule.get_instructions()
    instrs = list(filter(lambda x: x.startswith("nop("),instructions))
    # inst_filtered = filter(lambda x: (x.find("nop(JUMPDEST)")==-1) and (x.find("nop(JUMP)")==-1) and (x.find("nop(JUMPI)")==-1), instrs)
    return instrs

def get_jumpi_opcodes(rule):
    instructions = rule.get_instructions()[::-1]
    is_nop = True
    i = 0
    guard_opcodes = []
    while(i<len(instructions) and is_nop):
        instr = instructions[i]
        if instr.find("nop(")==-1:
            is_nop = False
        else:
            guard_opcodes.append(instr)
        i = i+1
    return guard_opcodes

def get_numguard_variables(instrs):
    jump_instr = instrs.pop(0)

    return len(instrs)

    # cond_instr = instrs.pop()
    # if cond_instr.find("nop(ISZERO")!=-1:
    #     return 1
    # else:
    #     return 2

def output_stack_rule(call_instr):
    stack_index = call_instr.find("s(")
    args = call_instr[stack_index:]
    vars_in = args.split(",")

    stack_vars = []
    
    for e in vars_in:
        if e.strip().startswith("s("):
            stack_vars.append(e.strip())

    return stack_vars

def output_stack_block(stack,guard_variables):
    output_rule = len(stack)
    return output_rule - guard_variables


def get_stack_variables(rule):
    index = rule.get_index_invars()
    return index

def generate_target_stack_idx(input_elems,list_opcodes):
    init_val = 0

    #print ("TARGET STACK")
    #print (input_elems)
    #print (list_opcodes)
    
    for op in list_opcodes:
        opcode = op[4:-1].strip()
        if opcode.startswith("PUSH"):
            vals = [0,0,1]
        else:
            vals = opcodes.get_opcode(opcode)
        init_val = init_val-vals[1]+vals[2]
    
    seq = range(0,input_elems+init_val) # if input_elems !=-1 else range(0,input_elems+init_val+1)
    target_vars = list(map(lambda x: "s("+str(x)+")",seq))
    return target_vars
    
def generate_vars_target_stack(guard_instrs, call,opcodes):
    ##print (opcodes)
    stack_rule = output_stack_rule(call)
    #num_target_stack = output_stack_block(stack_rule,guard_instrs)
    if call.find("call(block")!=-1 and "nop(JUMP)" in opcodes:
        num_target_stack = len(stack_rule)+1
    else:
        num_target_stack = len(stack_rule)
    seq = range(0,num_target_stack)
    target_vars = list(map(lambda x: "s("+str(x)+")",seq))
    return target_vars

def contained_in_source_stack(v,instructions,source_stack):
    contained = True
    i = 0

    if v not in source_stack:
        return False
    
    if instructions == []:
        contained = True
    else:
        
        while(i<len(instructions)):
            pos_var = instructions[i].find(v)

            if pos_var!=-1:
                pos_equals = instructions[i].find("=")
                if pos_equals != -1 and  pos_var < pos_equals:
                    return False
            i+=1

    return contained


def get_encoding_init_block(instructions,source_stack):
    global s_dict
    global u_dict

    old_sdict = dict(s_dict)
    old_u_dict = dict(u_dict)

    i = 0
    opcodes = []
    push_values = []
    
    # print("MIRA")
    # print(instructions)

    # print(instructions)
    while(i<len(instructions)):
        if instructions[i].startswith("nop("):
            instr = instructions[i][4:-1].strip()
            if instr.startswith("DUP") or instr.startswith("SWAP") or instr.startswith("PUSH") or instr.startswith("POP"):
                if instr.startswith("PUSH") and instr.find("DEPLOYADDRESS") == -1 and instr.find("SIZE") ==-1:
                    value = instructions[i-1].split("=")[-1].strip()
                    if value.find("pushtag")!=-1 or value.find("push#[$]")!=-1 or value.find("push[$]")!=-1 or value.find("pushdata")!=-1 or value.find("pushimmutable")!=-1:
                        pos = value.find("(")
                        int_val = value[pos+1:-1]
                        # print(int_val)
                        push_values.append(int_val)

                        var = instructions[i-1].split("=")[0].strip()
                        instructions_without_nop = list(filter(lambda x: not x.startswith("nop("), instructions[:i]))
                        instructions_reverse = instructions_without_nop[::-1]
                        # print("EMPIEZO EL NUEVO")  
                        search_for_value(var,instructions_reverse, source_stack, False)
                        # print(s_dict)
                        # print(u_dict)
                        opcodes.append((s_dict[var],u_dict[s_dict[var]]))
                    else:
                        opcodes.append(instr)
                        push_values.append(value) #normal push
                elif instr.startswith("PUSH") and (instr.find("DEPLOYADDRESS") !=-1 or instr.find("SIZE") !=-1):
                    var = instructions[i-1].split("=")[0].strip()

                    instructions_without_nop = list(filter(lambda x: not x.startswith("nop("), instructions[:i]))
                    instructions_reverse = instructions_without_nop[::-1]
                    # print("EMPIEZO EL NUEVO")  
                    search_for_value(var,instructions_reverse, source_stack, False)
                    # print(s_dict)
                    # print(u_dict)
                    opcodes.append((s_dict[var],u_dict[s_dict[var]]))
                    
                else: #DUP SWAP POP
                    opcodes.append(instr)
            else:
                #non-interpreted function
                var = instructions[i-1].split("=")[0].strip()

                instructions_without_nop = list(filter(lambda x: not x.startswith("nop("), instructions[:i]))
                instructions_reverse = instructions_without_nop[::-1]
                # print("EMPIEZO EL NUEVO")  
                search_for_value(var,instructions_reverse, source_stack, False)
                # print(s_dict)
                # print(u_dict)
                opcodes.append((s_dict[var],u_dict[s_dict[var]]))
                # print(u_dict[s_dict[var]])
        i+=1

    # print("ANTES")
    # print(instructions)
    # print(opcodes)
        
    new_opcodes = []
    init_user_def = []
    for i in range(len(opcodes)):
        if isinstance(opcodes[i],tuple):
            instruction = opcodes[i]

            u_var = instruction[0]
            args_exp = instruction[1][0]
            arity_exp = instruction[1][1]

            # print(user_def_counter)
            # print(already_defined_userdef)
            
            user_def = build_initblock_userdef(u_var,args_exp,arity_exp)
            init_user_def+=user_def
            for e in user_def:
                new_opcodes.append(e["id"])
        else:
            new_opcodes.append(opcodes[i])

    # new_opcodes = evaluate_constants(new_opcodes,init_user_def)

    # print(instructions)
    # print(new_opcodes)

    # print("*************")
    init_info = {}
    init_info["opcodes_seq"] = new_opcodes
    init_info["non_inter"] = init_user_def
    init_info["push_vals"] = list(map(lambda x: int(x),push_values))

    return init_info



def search_for_value(var, instructions,source_stack,evaluate = True):
    global s_counter
    global s_dict

    search_for_value_aux(var,instructions,source_stack,0,evaluate)

    # print(s_dict)
    # print(u_dict)
    # print("???????????????????????????")
    
def search_for_value_aux(var, instructions,source_stack,level,evaluate = True):
    global s_counter
    global s_dict
    global u_counter
    global u_dict
    
    i = 0
    found = False
    vars_instr = " "

    # print ("BUSCANDOOO")
    # print (var)
    # print (instructions)
    
    while(i<len(instructions) and not(found)):

        instr = instructions[i]
        vars_instr = instr.split("=")
        if vars_instr[0].strip().startswith(var):
            found = True
           
        i+=1
    level+=i
    if found:
        value = vars_instr[1].strip()
    else:
        value = var.strip()

    ##print (value)
    ##print ("------------------------")
        
    new_vars, funct = get_involved_vars(value,vars_instr[0])
    
    if len(new_vars) == 1:
        
        in_sourcestack = contained_in_source_stack(new_vars[0],instructions[i:],source_stack)
    
        if in_sourcestack or is_integer(new_vars[0])!=-1:
            if is_integer(new_vars[0])!=-1:
                val = int(new_vars[0])
            else:
                val = new_vars[0]
            update_unary_func(funct,var,new_vars[0],evaluate)
            
        else:
            if new_vars[0] not in zero_ary:
                search_for_value_aux(new_vars[0],instructions[i:],source_stack,level,evaluate)
                val = s_dict[new_vars[0]]
            else:
                val = new_vars[0]
            update_unary_func(funct,var,val,evaluate)
            
    else:
    
        u_var = create_new_svar()
        s_dict_old = dict(s_dict)

        values = {}

        for v in new_vars:

            search_for_value_aux(v,instructions[i:],source_stack,level,evaluate)
    
            values[v] = s_dict[v]

        exp_join = rebuild_expression(new_vars,funct,values,level,evaluate)
        r = exp_join[0]
        exp = (exp_join[1],exp_join[2])

        
        if r:
            s_dict[var] = exp[0]

        else:

            new_u, defined = is_already_defined(exp)
            if defined:
                u_var = new_u
            else:
                u_dict[u_var] = exp

            s_dict = s_dict_old
        
            s_dict[var] = u_var

def is_already_defined(elem):
    for u_var in u_dict.keys():
        if elem == u_dict[u_var]:
            return u_var, True

    return -1, False
    
def update_unary_func(func,var,val,evaluate):
    global s_dict
    global u_dict
    global gas_saved_op    
    
    if func != "":

        if is_integer(val)!=-1 and (func=="not" or func=="iszero") and evaluate:
            if func == "not":
                val_end = ~(int(val))+2**256
                gas_saved_op+=3
                
            elif func == "iszero":
                aux = int(val)
                val_end = 1 if aux == 0 else 0
                gas_saved_op+=3
                
            s_dict[var] = val_end
                
        else:
        
            u_var = create_new_svar()

            if val in zero_ary:
                arity = 0
            else:
                arity = 1

            elem = ((val,func),arity)
            new_uvar, defined = is_already_defined(elem)
            if defined:
                s_dict[var] = new_uvar
                #relative_pos_load(func,elem,new_uvar)
            else:
                u_dict[u_var] = elem
                s_dict[var] = u_var
                #relative_pos_load(func,elem,u_var)
    else:
        s_dict[var] = val

def get_involved_vars(instr,var):
    var_list = []
    funct = ""

    if instr.find("mload(")!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("mload(")
        arg0 = instr_new[pos+6:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "mload"

    elif instr.find("sload(")!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("sload(")
        arg0 = instr_new[pos+6:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "sload"
        
    elif instr.find("timestamp")!=-1:
        var_list.append("timestamp")
        funct =  "timestamp"

    elif instr.find("msize")!=-1:
        var_list.append("msize")
        funct =  "msize"

    elif instr.find("sha3(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("sha3(")
        arg01 = instr[pos+5:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "sha3"

    elif instr.find("keccak256(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("keccak256(")
        arg01 = instr[pos+10:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "keccak256"

        
    elif instr.find("signextend(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("signextend(")
        arg01 = instr[pos+11:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)
        funct = "signextend"

    elif instr.find("create(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("create(")
        arg012 = instr[pos+7:-1]
        var012 = arg012.split(",")
        var0 = var012[0].strip()
        var1 = var012[1].strip()
        var2 = var012[2].strip()
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        funct = "create"

    elif instr.find("create2(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("create2(")
        arg0123 = instr[pos+8:-1]
        var0123 = arg0123.split(",")
        var0 = var0123[0].strip()
        var1 = var0123[1].strip()
        var2 = var0123[2].strip()
        var3 = var0123[3].strip()
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        var_list.append(var3)
        funct = "create2"

    elif instr.find("extcodesize",0)!=-1:
        var0 = var.strip()
        var_list.append(var0)
        funct = "extcodesize"

    elif instr.find("extcodehash",0)!=-1:
        var0 = var.strip()
        var_list.append(var0)
        funct = "extcodehash"

    elif instr.find("returndatasize",0)!=-1:
        var_list.append("returndatasize")
        funct = "returndatasize"

    elif instr.find("and(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("and(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "and"
        
    elif instr.find("not(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("not(")
        arg0 = instr[pos+4:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "not"
        
    elif instr.find("xor(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("xor(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "xor"

    elif instr.find("or(",0)!=-1:
        instr_new = instr.strip("\n")
        pos = instr_new.find("or(")
        arg01 = instr[pos+3:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "or"
    
    elif instr.startswith("eq("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("eq(")
        arg01 = instr[pos+3:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        if var1 =="0":
            
            var_list.append(var0)
            funct = "iszero"
        else:
            var_list.append(var0)
            var_list.append(var1)
            funct = "eq"
    
    elif instr.startswith("lt("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("lt(")
        arg01 = instr[pos+3:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "lt"

    elif instr.startswith("slt("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("slt(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "slt"
    
    elif instr.startswith("gt("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("gt(")
        arg01 = instr[pos+3:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "gt"

    elif instr.startswith("sgt("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("sgt(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "sgt"

    elif instr.startswith("byte("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("byte(")
        arg01 = instr[pos+5:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "byte"

    elif instr.find("*")!=-1:
        if instr.find("%")!=-1: #MULMOD
            instr_new = instr.strip("\n")
            args012 = instr_new.split("%")
            args01 = args012[0].strip()
            var2 = args012[1].strip()

            vars01 = args01.split("*")
            var0 = vars01[0][1:].strip()
            var1 = vars01[1][:-1].strip()

            var_list.append(var0)
            var_list.append(var1)
            var_list.append(var2)

            funct = "*"
            
        else: #MUL

            instr_new = instr.strip("\n")
            var01 = instr_new.split("*")
            var0 = var01[0].strip()
            var1 = var01[1].strip()
            var_list.append(var0)
            var_list.append(var1)

            funct = "*"
            
    elif instr.find("+")!=-1:
        if instr.find("%")!=-1: #ADDMOD
            instr_new = instr.strip("\n")
            args012 = instr_new.split("%")
            args01 = args012[0].strip()
            var2 = args012[1].strip()

            vars01 = args01.split("+")
            var0 = vars01[0][1:].strip()
            var1 = vars01[1][:-1].strip()

            var_list.append(var0)
            var_list.append(var1)
            var_list.append(var2)

            funct = "+"
            
        else: #ADD
            instr_new = instr.strip("\n")
            var01 = instr_new.split("+")
            var0 = var01[0].strip()
            var1 = var01[1].strip()
            var_list.append(var0)
            var_list.append(var1)

            funct = "+"

    elif instr.find("-")!=-1:
        instr_new = instr.strip("\n")
        var01 = instr_new.split("-")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "-"

    elif instr.find("/")!=-1:
        instr_new = instr.strip("\n")
        var01 = instr_new.split("/")

        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "/"

    elif instr.find("^")!=-1:
        instr_new = instr.strip("\n")
        var01 = instr_new.split("^")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "^"

    elif instr.find("%")!=-1:
        instr_new = instr.strip("\n")
        var01 = instr_new.split("%")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "%"


    elif instr.startswith("shr("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("shr(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "shr"

    elif instr.startswith("shl("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("shl(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "shl"

    elif instr.startswith("sar("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("sar(")
        arg01 = instr[pos+4:-1]
        var01 = arg01.split(",")
        var0 = var01[0].strip()
        var1 = var01[1].strip()
        var_list.append(var0)
        var_list.append(var1)

        funct = "sar"
        
    elif instr.find("pushdeployaddress")!=-1:
        var_list.append("pushdeployaddress")
        funct =  "pushdeployaddress"

    elif instr.find("pushsize")!=-1:
        var_list.append("pushsize")
        funct =  "pushsize"

        
    elif instr.find("address")!=-1:
        var_list.append("address")
        funct =  "address"

    # elif instr.startswith("pc"):
    #     var_list.append("pc")
    #     funct =  "pc"
    
    elif instr.find("blockhash")!=-1:
        
        var0 = var.strip()
        var_list.append(var0)

        funct = "blockhash"

    elif instr.find("calldataload")!=-1:
        
        var0 = var.strip()
        var_list.append(var0)
        funct = "calldataload"

    elif instr.find("selfbalance")!=-1:
        var_list.append("selfbalance")
        funct =  "selfbalance"

        
    elif instr.find("balance")!=-1:
        var0 = var.strip()
        var_list.append(var0)
        funct = "balance"

    elif instr.find("chainid")!=-1:
        var_list.append("chainid")
        funct =  "chainid"

    elif instr.find("origin")!=-1:
        var_list.append("origin")
        funct =  "origin"

    elif instr.find("caller")!=-1:
        var_list.append("caller")
        funct =  "caller"

    elif instr.find("callvalue")!=-1:
        var_list.append("callvalue")
        funct =  "callvalue"

    elif instr.find("codesize")!=-1:
        var_list.append("codesize")
        funct =  "codesize"

    elif instr.find("gaslimit",0)!=-1:
        var_list.append("gaslimit")
        funct = "gaslimit"
            
    elif instr.find("gasprice")!=-1:
        var_list.append("gasprice")
        funct =  "gasprice"

    elif instr.find("gas")!=-1:
        var_list.append("gas")
        funct =  "gas"
    
    elif instr.find("calldatasize")!=-1:
        var_list.append("calldatasize")
        funct =  "calldatasize"

    elif instr.find("number")!=-1:
        var_list.append("number")
        funct =  "number"

    elif instr.find("difficulty")!=-1:
        var_list.append("difficulty")
        funct =  "difficulty"

    elif instr.find("coinbase")!=-1:
        var_list.append("coinbase")
        funct =  "coinbase"

    elif instr.startswith("call_ext("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("call_ext(")
        arg = instr[pos+9:-1]
        vars06 = arg.split(",")
        var0 = vars06[0].strip()
        var1 = vars06[1].strip()
        var2 = vars06[2].strip()
        var3 = vars06[3].strip()
        var4 = vars06[4].strip()
        var5 = vars06[5].strip()
        var6 = vars06[6].strip()
                                
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        var_list.append(var3)
        var_list.append(var4)
        var_list.append(var5)
        var_list.append(var6)

        funct = "call"

    elif instr.startswith("callcode("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("callcode(")
        arg = instr[pos+9:-1]
        vars06 = arg.split(",")
        var0 = vars06[0].strip()
        var1 = vars06[1].strip()
        var2 = vars06[2].strip()
        var3 = vars06[3].strip()
        var4 = vars06[4].strip()
        var5 = vars06[5].strip()
        var6 = vars06[6].strip()
                                
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        var_list.append(var3)
        var_list.append(var4)
        var_list.append(var5)
        var_list.append(var6)

        funct = "callcode"

    elif instr.startswith("callstatic("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("callstatic(")
        arg = instr[pos+11:-1]
        vars06 = arg.split(",")
        var0 = vars06[0].strip()
        var1 = vars06[1].strip()
        var2 = vars06[2].strip()
        var3 = vars06[3].strip()
        var4 = vars06[4].strip()
        var5 = vars06[5].strip()
        var6 = vars06[6].strip()
                                
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        var_list.append(var3)
        var_list.append(var4)
        var_list.append(var5)
        var_list.append(var6)

        funct = "callstatic"

    elif instr.startswith("delegatecall_ext("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("delegatecall_ext(")
        arg = instr[pos+17:-1]
        vars05 = arg.split(",")
        var0 = vars05[0].strip()
        var1 = vars05[1].strip()
        var2 = vars05[2].strip()
        var3 = vars05[3].strip()
        var4 = vars05[4].strip()
        var5 = vars05[5].strip()
                                
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        var_list.append(var3)
        var_list.append(var4)
        var_list.append(var5)

        funct = "delegatecall"

    elif instr.startswith("staticcall_ext("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("staticcall_ext(")
        arg = instr[pos+15:-1]
        vars05 = arg.split(",")
        var0 = vars05[0].strip()
        var1 = vars05[1].strip()
        var2 = vars05[2].strip()
        var3 = vars05[3].strip()
        var4 = vars05[4].strip()
        var5 = vars05[5].strip()
                                
        var_list.append(var0)
        var_list.append(var1)
        var_list.append(var2)
        var_list.append(var3)
        var_list.append(var4)
        var_list.append(var5)

        funct = "staticcall"

    elif instr.startswith("pushtag("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("pushtag(")
        arg0 = instr[pos+8:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "pushtag"


    elif instr.startswith("push#[$]("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("push#[$](")
        arg0 = instr[pos+9:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "push#[$]"

    elif instr.startswith("push[$]("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("push[$](")
        arg0 = instr[pos+8:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "push[$]"


    elif instr.startswith("pushdata("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("pushdata(")
        arg0 = instr[pos+9:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "pushdata"

    elif instr.startswith("pushimmutable("):
        instr_new = instr.strip("\n")
        pos = instr_new.find("pushimmutable(")
        arg0 = instr[pos+14:-1]
        var0 = arg0.strip()
        var_list.append(var0)

        funct = "pushimmutable"

        
    else:
        var_list.append(instr)
        funct = ""
   
    return var_list, funct

def evaluate_expression(funct,val0,val1):
    if funct == "+":
        return val0+val1
    elif funct == "-":
        return val0-val1
    elif funct == "*":
        return val0*val1
    elif funct == "/":
        return val0/val1
    elif funct == "^":
        return val0**val1
    elif funct == "and":
        return val0&val1
    elif funct == "or":
        return val0|val1
    elif funct == "xor":
        return val0^val1
    elif funct == "%":
        return val0%val1
    elif funct == "eq":
        return 1 if val0==val1 else 0
    elif funct == "gt":
        return 1 if val0>val1 else 0
    elif funct == "lt":
        return 1 if val0 < val1 else 0
    elif funct == "shr":
        return math.floor(val1/(2**val0))
    elif funct == "shl":
        return (val1*(2**val0)) % (2**256)
    elif funct == "sar":
        return math.floor(val1/(2**val0))

def evaluate_expression_ter(funct,val0,val1,val2):
    if funct == "+":
        aux = val0+val1
        return aux%val2
    elif funct == "*":
        aux = val0*val1
        return aux%val2

    
def compute_binary(expression,level):
    global discount_op
    global saved_push
    global gas_saved_op
    global already_considered

    
    v0 = expression[0]
    v1 = expression[1]
    funct = expression[2]

    r, vals = all_integers([v0,v1])

    if r and funct in ["+","-","*","/","^","and","or","xor","%","eq","gt","lt","shl","shr","sar"]:

        exp_str = str(funct)+" "+str(vals[0])+" "+str(vals[1])+","+str(level)
        exp_str_comm = str(funct)+" "+str(vals[1])+" "+str(vals[0])+","+str(level)

        val = evaluate_expression(funct,vals[0],vals[1])
        
        if funct in ["*","/","%"]:
            gas_saved_op+=5
        else:
            gas_saved_op+=3

        saved_push+=2
        if exp_str not in already_considered:
            if (funct in ["+","*","and","or","xor","eq"]) and (exp_str_comm not in already_considered):
                discount_op+=2
                print("[RULE]: Evaluate expression "+str(expression))

            elif funct not in ["+","*","and","or","xor","eq"]:
                discount_op+=2
                print("[RULE]: Evaluate expression "+str(expression))


        already_considered.append(exp_str)
        
        return True, val
        
    else:
        return False, expression

def compute_ternary(expression):
    global discount_op
    global saved_push
    global gas_saved_op
    
    v0 = expression[0]
    v1 = expression[1]
    v2 = expression[2]
    funct = expression[3]

    r, vals = all_integers([v0,v1,v2])
    if r and funct in ["+","*"]:
        val = evaluate_expression_ter(funct,vals[0],vals[1],vals[2])
        #print("[RULE]: Evaluate expression "+str(expression))
        gas_saved_op+=8
        saved_push+=3
        
        discount_op+=3
        return True, val
    else:
        return False, expression


def rebuild_expression(vars_input,funct,values,level,evaluate = True):

    if len(vars_input) == 2:
        v0 = values[vars_input[0]]
        v1 = values[vars_input[1]]
        expression = (v0, v1, funct)
        if evaluate:
            r, expression = compute_binary(expression,level)
        else:
            r = False
        arity = 2
    elif len(vars_input) == 3: #len == 3
        v0 = values[vars_input[0]]
        v1 = values[vars_input[1]]
        v2 = values[vars_input[2]]
        expression = (v0,v1,v2,funct)
        if evaluate:
            r, expression = compute_ternary(expression)
        else:
            r = False
        arity = 3

    else:
        variables = []
        for v in vars_input:
            variables.append(values[v])
        variables.append(funct)
        expression = tuple(variables)
        r = False
        arity = len(vars_input)
    return r, expression, arity

def create_new_uvar():
    global u_counter

    var =  "u"+str(u_counter)
    u_counter+=1

    return var


def create_new_svar():
    global s_counter
    
    var =  "s("+str(s_counter)+")"
    s_counter+=1

    return var

  
def simplify_constants(opcodes_seq,user_def):
    for u in user_def:
        inpt = u["inpt_sk"]
        r, elems = all_integers(inpt)
        if r:
            result = evaluate(elems)
            
def generate_encoding(instructions,variables,source_stack,simplification=True):
    global s_dict
    global u_dict
    global variable_content

    instructions_reverse = instructions[::-1]
    u_dict = {}
    variable_content = {}
    for v in variables:
        s_dict = {}
        search_for_value(v,instructions_reverse, source_stack,simplification)
        variable_content[v] = s_dict[v]    
        
def generate_source_stack_variables(idx):
    ss_list = []
    
    for e in range(idx-1,-1,-1):
        ss_list.append("s("+str(e)+")")
    
    return ss_list
    
def get_s_counter(source_stack,target_stack):
    global s_counter

    ##print (source_stack)
    ##print (target_stack)
    max_ss = int(source_stack[0].strip()[2:-1]) if source_stack !=[] else -1
    max_ts = int(target_stack[0].strip()[2:-1]) if target_stack != [] else -1

    s_counter = max(max_ss,max_ts)
    s_counter+=1
    return s_counter


def compute_reverse_svar(var, max_idx):
    
    if str(var).startswith("s("):
        integer = int(var.strip()[2:-1])
    else:
        return var
    
    if integer<=max_idx:
        new_int = max_idx-integer
        new_var = "s("+str(new_int)+")"
    else:
        new_var = var
        
    return new_var

def compute_vars_set(sstack,tstack):
    vars_list = []

    vars_list = list(sstack)

    for user_ins in user_defins:
        output_vars = user_ins["outpt_sk"]
        input_vars = user_ins["inpt_sk"]
        potential_vars = output_vars+input_vars+tstack
        for v in potential_vars:
            if str(v).startswith("s(") and v not in vars_list:
                vars_list.append(v)
    vars_list.sort()
    return vars_list

#When we are simplifying user_def_init = []
def recompute_vars_set(sstack,tstack,userdef,user_def_init):
    vars_list = []

    vars_list = list(sstack)

    
    user_def_instr = userdef+user_def_init
    
    for user_ins in user_def_instr:
        output_vars = user_ins["outpt_sk"]
        input_vars = user_ins["inpt_sk"]
        potential_vars = output_vars+input_vars+tstack
        for v in potential_vars:
            if str(v).startswith("s(") and v not in vars_list:
                vars_list.append(v)
    vars_list.sort()
    return vars_list

def compute_target_stack(tstack):
    new_vals = []
    for v in tstack:
        new_vals.append(variable_content[v])

    return new_vals

def check_all_pops(sstack, tsstack, user_def):
    if len(sstack) > 0 and tsstack == [] and user_def == []:
        return len(sstack)
    else:
        return -1

def compute_max_idx(max_ss,ss):
    if ss == []:
        return max_ss
    
    top_s = ss[0]
    idx_top = int(top_s[2:-1])

    return idx_top
    
def generate_json(block_name,ss,ts,max_ss_idx1,gas,opcodes_seq,subblock = None,simplification = True):
    global max_instr_size
    global num_pops
    global blocks_json_dict
    
    max_ss_idx = compute_max_idx(max_ss_idx1,ss)
    
    json_dict = {}

    new_ss = []
    new_ts = []

    ts_aux = compute_target_stack(ts)
    
    for v in ss:
        new_v = compute_reverse_svar(v,max_ss_idx)
        new_ss.append(new_v)

    for v in ts_aux:
        new_v = compute_reverse_svar(v,max_ss_idx)
        v =  is_integer(new_v)
        if v !=-1:
            new_ts.append(v)
        else:
            new_ts.append(new_v)

    for user_ins in user_defins:
        new_inpt_sk = []

        for v in user_ins["inpt_sk"]:
            new_v = compute_reverse_svar(v,max_ss_idx)
            new_inpt_sk.append(new_v)

        user_ins["inpt_sk"] = new_inpt_sk

    remove_vars=[]

    vars_list = compute_vars_set(new_ss,new_ts)

    if simplification:
        new_user_defins,new_ts = apply_all_simp_rules(user_defins,vars_list,new_ts)
        apply_all_comparison(new_user_defins,new_ts)
    else:
        new_user_defins = user_defins


    if simplification:
        vars_list = recompute_vars_set(new_ss,new_ts,new_user_defins,[])
    else:
        vars_list = recompute_vars_set(new_ss,new_ts,new_user_defins,opcodes_seq["non_inter"])
        
    total_inpt_vars = []
    
    for user_ins in new_user_defins:
        for v in user_ins["inpt_sk"]:
            if str(v).startswith("s(") and v not in total_inpt_vars:
                total_inpt_vars.append(v)

    optimized_json(total_inpt_vars,new_ss,new_ts,remove_vars)
    
    max_sk_sz_idx = max(len(vars_list),max_stack_size)
        
    for s in remove_vars:
        if s in vars_list:
            idx = vars_list.index(s)
            vars_list.pop(idx)


    not_used = get_not_used_stack_variables(new_ss,new_ts,total_inpt_vars)

    num = check_all_pops(new_ss, new_ts, user_defins)

    if num !=-1:
        max_instr_size = num
        num_pops = num

    json_dict["init_progr_len"] = max_instr_size-discount_op
    json_dict["max_progr_len"] = max_instr_size
    json_dict["max_sk_sz"] = max_sk_sz_idx-len(remove_vars)
    json_dict["vars"] = vars_list
    json_dict["src_ws"] = new_ss
    json_dict["tgt_ws"] = new_ts
    json_dict["user_instrs"] = new_user_defins
    json_dict["current_cost"] = gas
    if not simplification:
        json_dict["init_info"] = opcodes_seq

        
    if subblock != None:
        block_nm = block_name+"."+str(subblock)
    else:
        block_nm = block_name

    blocks_json_dict[block_nm] = json_dict


    if simplification:
        if "jsons" not in os.listdir(gasol_path):
            os.mkdir(json_path)

        with open(json_path+"/"+source_name+"_"+cname+"_"+block_nm+"_input.json","w") as json_file:
            json.dump(json_dict,json_file)


def get_not_used_stack_variables(new_ss,new_ts,total_inpt_vars):
    not_used = []

    for s in new_ss:
        if (s not in new_ts) and (s not in total_inpt_vars):
            not_used.append(s)

    return not_used
        
def optimized_json(inpt_vars,ss,ts,remove_vars):
    end = False
    i = len(ss)
    
    if ss == [] or ts == []:
        return

    
    while(i>0 and not end):
        same_pos = ss[-1] == ts[-1]
        involved = ts[-1] in inpt_vars
        dups = ts[-1] in ts[:-1]

        if same_pos and not involved and not dups:
            remove_vars.append(ts[-1])
            ss.pop()
            ts.pop()
            if ts == [] or ss == []:
                return
        else:
            end = True
        i-=1

def build_initblock_userdef(u_var,args_exp,arity_exp):
    if arity_exp ==0 or arity_exp == 1:
        funct = args_exp[1]
        args = args_exp[0]

        # print(u_var)
        # print(funct)
        # print(args)
        # print(arity_exp)
        is_new, obj = generate_userdefname(u_var,funct,[args],arity_exp)

        # print("*/*/*/*//*/*/*/*/*/**/")
        # print(obj)
        
        return [obj]
            
    elif arity_exp == 2:
        funct = args_exp[2]
        args = [args_exp[0],args_exp[1]]
        is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)
        return [obj]
    
    elif arity_exp == 3:
        funct = args_exp[3]

        if funct == "+" or funct == "*":
            
            new_uvar = create_new_svar()
            args01 = [args_exp[0],args_exp[1]]
            is_new, obj = generate_userdefname(new_uvar,funct,args01,arity_exp)
            
            funct = "%"
            if not is_new:
                u_var_aux = obj["outpt_sk"][0]
            else:
                u_var_aux = new_uvar
                
            args = [u_var_aux,args_exp[2]]

            is_new, obj1 = generate_userdefname(u_var,funct,args,arity_exp)
            
            return [obj, obj1]
        else:

            args = [args_exp[0],args_exp[1],args_exp[2]]
            is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)
            
            return [obj]
    else:
        funct = args_exp[-1]
        args = []
        for v in args_exp[:-1]:
            args.append(v)
            
        is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)

        return [obj]

        
def build_userdef_instructions():
    global user_defins
    global already_defined_userdef
    
    already_defined_userdef = []

    u_dict_sort = sorted(u_dict.keys())
    for u_var in u_dict_sort:
        exp = u_dict[u_var]
        arity_exp = exp[1]
        args_exp = exp[0]

        if arity_exp ==0 or arity_exp == 1:
            funct = args_exp[1]
            args = args_exp[0]
            
            is_new, obj = generate_userdefname(u_var,funct,[args],arity_exp)

            
            if not is_new and funct not in ["gas","timestamp","returndatasize"]:
                modified_svariable(u_var, obj["outpt_sk"][0])

            else:
                user_defins.append(obj)
            
        elif arity_exp == 2:
            funct = args_exp[2]
            args = [args_exp[0],args_exp[1]]
            is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)

            if not is_new:
                modified_svariable(u_var, obj["outpt_sk"][0])

            else:
                user_defins.append(obj)

        elif arity_exp == 3:
            funct = args_exp[3]

            if funct == "+" or funct == "*":
            
                new_uvar = create_new_svar()
                args01 = [args_exp[0],args_exp[1]]
                is_new, obj = generate_userdefname(new_uvar,funct,args01,arity_exp)

                if not is_new:
                    modified_svariable(new_uvar, obj["outpt_sk"][0])

                else:
                    user_defins.append(obj)

                funct = "%"
                if not is_new:
                    u_var_aux = obj["outpt_sk"][0]
                else:
                    u_var_aux = new_uvar
                
                args = [u_var_aux,args_exp[2]]

                is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)

                if not is_new:
                    modified_svariable(new_uvar, obj["outpt_sk"][0])

                else:
                    user_defins.append(obj)

            else:

                args = [args_exp[0],args_exp[1],args_exp[2]]
                is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)

                if not is_new:
                    modified_svariable(u_var, obj["outpt_sk"][0])

                else:
                    user_defins.append(obj)
        else:
            funct = args_exp[-1]
            args = []
            for v in args_exp[:-1]:
                args.append(v)

            is_new, obj = generate_userdefname(u_var,funct,args,arity_exp)

            if not is_new:
                modified_svariable(u_var, obj["outpt_sk"][0])

            else:
                user_defins.append(obj)
                
def generate_userdefname(u_var,funct,args,arity):
    global user_def_counter
    global already_defined_userdef

    # print("A VER A VER")
    # print(funct)
    # print(user_def_counter)
    
    if funct.find("+") != -1:
        instr_name = "ADD"

    elif funct.find("-") != -1:
        instr_name = "SUB"

    elif funct.find("*") !=-1:
        instr_name = "MUL"

    elif funct.find("/") !=-1:
        instr_name = "DIV"
        
    elif funct.find("^") !=-1:
        instr_name = "EXP"

    elif funct.find("%") !=-1:
        instr_name = "MOD"

    elif funct.find("and") !=-1:
        instr_name = "AND"

    elif funct.find("origin")!=-1:
        instr_name = "ORIGIN"

    elif funct.find("pushdeployaddress")!=-1:
        instr_name = "PUSHDEPLOYADDRESS"

    elif funct.find("pushsize")!=-1:
        instr_name = "PUSHSIZE"

        
    elif funct.find("xor") !=-1:
        instr_name = "XOR"
        
    elif funct.find("or") !=-1:
        instr_name = "OR"

    elif funct.find("not") !=-1:
        instr_name = "NOT"

    elif funct.find("gt") !=-1:
        instr_name = "GT"

    elif funct.find("sgt") !=-1:
        instr_name = "SGT"

    elif funct.find("shr") !=-1:
        instr_name = "SHR"

    elif funct.find("shl") !=-1:
        instr_name = "SHL"

    elif funct.find("sar") !=-1:
        instr_name = "SAR"
        
    elif funct.startswith("lt"):
        instr_name = "LT"

    elif funct.find("slt") !=-1:
        instr_name = "SLT"

    elif funct.find("selfbalance") !=-1:
        instr_name = "SELFBALANCE"

    elif funct.find("extcodehash") !=-1:
        instr_name = "EXTCODEHASH"

    elif funct.find("chainid") !=-1:
        instr_name = "CHAINID"

    elif funct.find("create2") !=-1:
        instr_name = "CREATE2"

    elif funct.find("byte") !=-1:
        instr_name = "BYTE"

    elif funct.find("eq") !=-1:
        instr_name = "EQ"

    elif funct.find("iszero") !=-1:
        instr_name = "ISZERO"
        

    elif funct.find("caller")!=-1:
        instr_name = "CALLER"

    elif funct.find("callvalue")!=-1:
        instr_name = "CALLVALUE"
        
    elif funct.find("calldataload")!=-1:
        instr_name = "CALLDATALOAD"
    
    elif funct.find("address")!=-1:
        instr_name = "ADDRESS"

    elif funct.find("calldatasize")!=-1:
        instr_name = "CALLDATASIZE"
        
    elif funct.find("number")!=-1:
        instr_name = "NUMBER"

    elif funct.find("gasprice")!=-1:
        instr_name = "GASPRICE"

    elif funct.find("difficulty")!=-1:
        instr_name = "DIFFICULTY"

    elif funct.find("blockhash")!=-1:
        instr_name = "BLOCKHASH"

    elif funct.find("balance")!=-1:
        instr_name = "BALANCE"

    elif funct.find("coinbase")!=-1:
        instr_name = "COINBASE"

    elif funct.find("mload")!=-1:
        instr_name = "MLOAD"

    elif funct.find("sload")!=-1:
        instr_name = "SLOAD"

    elif funct.find("timestamp")!=-1:
        instr_name = "TIMESTAMP"

    elif funct.find("msize")!=-1:
        instr_name = "MSIZE"
        
    elif funct.find("signextend")!=-1:
        instr_name = "SIGNEXTEND"

    elif funct.find("extcodesize")!=-1:
        instr_name = "EXTCODESIZE"

    elif funct.find("create")!=-1:
        instr_name = "CREATE"

    elif funct.find("gaslimit")!=-1:
        instr_name = "GASLIMIT"
    
    elif funct.find("codesize")!=-1:
        instr_name = "CODESIZE"
        
    elif funct.find("sha3")!=-1:
        instr_name = "SHA3"

    elif funct.find("keccak256")!=-1:
        instr_name = "KECCAK256"

        
    elif funct.find("gas")!=-1:
        instr_name = "GAS"

    elif funct.find("returndatasize")!=-1:
        instr_name = "RETURNDATASIZE"

    elif funct.find("callcode")!=-1:
        instr_name = "CALLCODE"

    elif funct.find("delegatecall")!=-1:
        instr_name = "DELEGATECALL"

    elif funct.find("staticcall")!=-1:
        instr_name = "STATICCALL"

    elif funct.find("callstatic")!=-1:
        instr_name = "CALLSTATIC"

    elif funct.find("call")!=-1:
        instr_name = "CALL"

    #Yul opcodes
    
    elif funct.find("pushtag")!=-1:
        instr_name = "PUSHTAG"

    elif funct.find("push#[$]")!=-1:
        instr_name = "PUSH#[$]"

    elif funct.find("push[$]")!=-1:
        instr_name = "PUSH[$]"

    elif funct.find("pushdata")!=-1:
        instr_name = "PUSHDATA"

    elif funct.find("pushimmutable")!=-1:
        instr_name = "PUSHIMMUTABLE"

        
    #TODO: Add more opcodes
    
    if instr_name in already_defined_userdef:
        defined = check_inputs(instr_name,args)
    else:
        defined = -1
        # if instr_name not in ["PUSHTAG","PUSH#[$]","PUSH[$]","PUSHDATA"]:
        already_defined_userdef.append(instr_name)
            
    if defined == -1:
        obj = {}

        if funct == args: #0-ary functions
            name = instr_name
        else:
            idx = user_def_counter.get(instr_name,0)    
            name = instr_name+"_"+str(idx)

        args_aux = []
        for e in args:
            val = is_integer(e)
            if val != -1:
                args_aux.append(val)
            else:
                args_aux.append(e)
                
        obj["id"] = name
        obj["opcode"] = process_opcode(str(opcodes.get_opcode(instr_name)[0]))
        obj["disasm"] = instr_name
        obj["inpt_sk"] = [] if arity==0 or instr_name in ["PUSHTAG","PUSH#[$]","PUSH[$]","PUSHDATA","PUSHIMMUTABLE"] else args_aux
        obj["outpt_sk"] = [u_var]
        obj["gas"] = opcodes.get_ins_cost(instr_name)
        obj["commutative"] = True if instr_name in commutative_bytecodes else False
        if instr_name in ["PUSHTAG","PUSH#[$]","PUSH[$]","PUSHDATA","PUSHIMMUTABLE"]:
            obj["value"] = args_aux
        user_def_counter[instr_name]=idx+1

        new = True
    else:
        obj = defined
        new = False


    return new, obj

def times_used_userdef_instructions(user_def,tstack,all_input_values):
    all_vars = tstack+all_input_values
    for instr in user_def:
        [output] = instr["outpt_sk"]
        used = list(filter(lambda x : str(x).strip() == output.strip(),all_vars))
        instr["times_used"] = len(used)

def process_opcode(result):
    op_val = hex(int(result))[2:]

    if (int(op_val,16)<12):
        op_val = "0"+str(op_val)
    return op_val

def modified_svariable(old_uvar, new_uvar):
    global s_dict
    global u_dict


    for s_var in s_dict.keys():
        if str(s_dict[s_var]).find(old_uvar)!=-1:
            s_dict[s_var] = new_uvar

    for u_var in u_dict.keys():
        pos = old_uvar in u_dict[u_var][0]
        if pos:
            elems = list(u_dict[u_var][0])
            pos_var = elems.index(old_uvar)
            elems[pos_var] = new_uvar
            new_val = (tuple(elems),u_dict[u_var][1])
            u_dict[u_var] = new_val
    
def check_inputs(instr_name,args_aux):
    
    args = []
    for a in args_aux:
        if is_integer(a) !=-1:
            args.append(int(a))
        else:
            args.append(a)
            
    
    for elem in user_defins:
        name = elem["disasm"]
        if name == instr_name and name not in ["PUSHTAG","PUSH#[$]","PUSH[$]","PUSHDATA","PUSHIMMUTABLE"]:
            input_variables = elem["inpt_sk"]
            if instr_name in commutative_bytecodes:
                if ((input_variables[0] == args[1]) and (input_variables[1] == args[0])) or ((input_variables[0] == args[0]) and (input_variables[1] == args[1])):
                    return elem
                
            else:
                i = 0
                equals = True
                while (i <len(input_variables) and equals):
                    
                    if args[i] !=input_variables[i]:
                        equals = False
                    i+=1

                if equals:
                    return elem

        elif name == instr_name and name in ["PUSHTAG","PUSH#[$]","PUSH[$]","PUSHDATA","PUSHIMMUTABLE"]:
            input_variables = elem["value"]
            i = 0
            equals = True
            while (i <len(input_variables) and equals):
                    
                if args[i] !=input_variables[i]:
                    equals = False
                i+=1

            if equals:
                return elem

            
    return -1

def split_blocks(rule,opt = False,new_instr = []):
    blocks = []
    
    ins_block = []

    if opt:
        instructions = new_instr
    else:
        instructions = rule.get_instructions()
    
    for ins in instructions:
        ins_block.append(ins)
        if ins.startswith("nop("):
            nop = ins[4:-1]
            
            if nop in split_block or nop in terminate_block:
                prev = ins_block[-2]
                blocks.append(ins_block)
                ins_block = [prev,ins]

    blocks.append(ins_block)
    
    return blocks
            


def get_max_stackindex_set(instructions):
    max_idx = float('-inf')
    for ins in instructions:
        vars_ins = ins.split("=")
        var = vars_ins[0].strip()

        idx = int(var[2:-1])
        
        if max_idx < idx:
            max_idx = idx
            
    return max_idx

def is_optimizable(opcode_instructions,instructions):
    ins_aux = list(map(lambda x: x.strip()[4:-1], opcode_instructions))
    ins = list(filter(lambda x: x in split_block or x in terminate_block, ins_aux))

    if ins_aux != [] and list(filter(lambda x: x.find("POP")==-1, ins_aux)) == []:
        return True
    
    if ins == []:

        return True if (instructions[:-1]!=[] or len(instructions)==1) else False
    else:
        return False

def translate_block(rule,instructions,opcodes,isolated,preffix,simp):
    global max_instr_size
    global max_stack_size
    global num_pops
    global gas_t
    
    source_stack_idx = get_stack_variables(rule)   
    
    if not isolated: 
        if "nop(JUMPI)" in opcodes:
            guards_op = get_jumpi_opcodes(rule)
            num_guard = get_numguard_variables(guards_op)
        else:
            guards_op = []
            num_guard = 0

    else:
        num_guard = 0
        guards_op = []
        
    if "nop(JUMP)" in opcodes or "nop(JUMPI)" in opcodes:
        max_instr_size = len(opcodes)-num_guard-1
    else:
        max_instr_size = len(opcodes)-num_guard

    max_instr_size = compute_max_program_len(opcodes, num_guard)

    if not isolated:
        pops = list(filter(lambda x: x.find("nop(POP)")!=-1,opcodes))
        num_pops = len(pops)
        x = list(filter(lambda x: (x.find("POP")==-1) and (x.find("JUMPDEST")==-1) and (x.find("JUMP")==-1)and(x.find("JUMPI")==-1),opcodes))
        if x == [] and num_pops >0:

            t_vars_idx = source_stack_idx-num_pops
            seq = range(0,t_vars_idx)
            t_vars = list(map(lambda x: "s("+str(x)+")",seq))[::-1]
            
        else:
            t_vars = generate_vars_target_stack(num_guard,instructions[-1],opcodes)[::-1]
    else:
        t_vars = generate_target_stack_idx(source_stack_idx,opcodes)[::-1]

    pops = list(filter(lambda x: x.find("nop(POP)")!=-1,opcodes))
    num_pops = len(pops)
    
    #print ("************")
    #print (rule.get_rule_name())
    #print ("Instructions:")
    #print (rule.get_instructions())
    #print ("Filtered opcodes:")
    #print (instructions)
    #print ("Opcodes")
    #print (opcodes)
    #print ("Get JUMPI Opcodes")
    #print (get_jumpi_opcodes(rule))
    #print ("Num Guards")
    #print (num_guard)
    #print ("Target Stack")
    #print (t_vars)

    source_stack = generate_source_stack_variables(source_stack_idx)
    get_s_counter(source_stack,t_vars)
    #print ("GENERATING ENCONDING")


    generate_encoding(instructions,t_vars,source_stack,simp)
    
    build_userdef_instructions()
    gas = get_block_cost(opcodes,len(guards_op))
    max_stack_size = max_idx_used(instructions,t_vars)
    
    if  gas!=0 and not is_identity_map(source_stack,t_vars):
        gas_t+=get_cost(original_opcodes)
        
        new_opcodes = compute_opcodes2write(opcodes,num_guard)

        if not simp:
            index, fin = find_sublist(rule.get_instructions(),new_opcodes)
            init_info = get_encoding_init_block(rule.get_instructions()[index:fin+1],source_stack)
        else:
            init_info = {}
        generate_json(preffix+rule.get_rule_name(),source_stack,t_vars,source_stack_idx-1,gas, init_info,simplification = simp)
        if simp:
            write_instruction_block(rule.get_rule_name(),new_opcodes)


def compute_opcodes2write(opcodes,num_guard):
    if "nop(JUMPDEST)" in opcodes:
        new_opcodes_aux = opcodes[1:]
    else:
        new_opcodes_aux = opcodes

    if "nop(JUMPI)" in new_opcodes_aux:
        new_opcodes = new_opcodes_aux[:-1-num_guard]
    elif "nop(JUMP)" in new_opcodes_aux:
        new_opcodes = new_opcodes_aux[:-1]
    else:
        new_opcodes = new_opcodes_aux

    return new_opcodes
        
def generate_subblocks(rule,list_subblocks,isolated,preffix,simplification):
    global gas_t
    
    source_stack_idx = get_stack_variables(rule)
    source_stack = generate_source_stack_variables(source_stack_idx)

    source_stack_idx-=1
    i = 0

    pops2remove = 0
    while(i < len(list_subblocks)-1):

        init_globals()
        block = list_subblocks[i]
        nop_instr = block[-1]
        last_instr = block[-2]

        ts_idx = compute_target_stack_subblock(last_instr,nop_instr)

        seq = range(ts_idx,-1,-1)
        target_stack = list(map(lambda x: "s("+str(x)+")",seq))

        new_nexts, pops2remove = translate_subblock(rule,block,source_stack,target_stack,source_stack_idx,i,list_subblocks[i+1],preffix,simplification,pops2remove)

        if new_nexts == []:
        #We update the source stack for the new block
            source_stack, source_stack_idx = get_new_source_stack(last_instr,nop_instr,ts_idx)
        else:
            new_block = new_nexts[0]

            new_idxstack= new_nexts[1] #it returns the last index of sstore

            list_subblocks[i+1] = new_block
            source_stack_idx = new_idxstack
            seq = range(source_stack_idx-1,-1,-1)
            source_stack = list(map(lambda x: "s("+str(x)+")",seq))
            
        i+=1

    instrs = list_subblocks[-1]

    if source_stack == []:
        source_stack_idx = -1

    block = instrs[2:]
    if block != []:
        translate_last_subblock(rule,block,source_stack,source_stack_idx,i,isolated,preffix,simplification,pops2remove)

    if compute_gast:
        gas_t+=get_cost(original_opcodes)

    
def translate_subblock(rule,instrs,sstack,tstack,sstack_idx,idx,next_block,preffix,simp,prev_pops):
    global max_instr_size
    global max_stack_size
    global num_pops
    global compute_gast
    
    if idx == 0:
        instructions = instrs[:-2]
    else:
        instructions = instrs[2:-2]
            
    rbr_ins_aux = list(filter(lambda x: x.find("nop(")==-1, instructions))
    instr = list(filter(lambda x: x!="" and x.find("skip")==-1, rbr_ins_aux))
    
    opcodes = list(filter(lambda x: x.find("nop(")!=-1,instructions))
    max_instr_size = compute_max_program_len(opcodes, 0)

    
    pops = list(filter(lambda x: x.find("nop(POP)")!=-1,opcodes))
    num_pops = len(pops)

    new_nexts = []
    
    if instr!=[]:
        get_s_counter(sstack,tstack)
        
        generate_encoding(instr,tstack,sstack,simp)
        build_userdef_instructions()
        gas = get_block_cost(opcodes,0)
        max_stack_size = max_idx_used(instructions,tstack)
        if max_stack_size!=0 and gas !=0 and not is_identity_map(sstack,tstack):
            compute_gast = True
            new_tstack,new_nexts = optimize_splitpop_block(tstack,sstack,next_block,opcodes)
            pops2remove = 0
            if new_nexts != []:
                pops2remove = new_nexts[2]
                # gas = gas+2*pops2remove
                max_instr_size+=pops2remove

            new_opcodes = compute_opcodes2write(opcodes,0)
            if not simp:
                index, fin = find_sublist(instructions,new_opcodes)
                init_info = get_encoding_init_block(instructions[index:fin+1],sstack)
            else:
                init_info = {}

            if prev_pops != 0:
                gas = gas+2*prev_pops
                
            generate_json(preffix+rule.get_rule_name(),sstack,new_tstack,sstack_idx,gas,init_info,subblock=idx,simplification = simp)
            if simp:
                write_instruction_block(rule.get_rule_name(),new_opcodes,subblock=idx)
            
        return new_nexts, pops2remove
    else:
        return [],0

            

def optimize_splitpop_block(tstack,source_stack,next_block,opcodes):
    
    i = 0
    target_stack = compute_target_stack(tstack)
    opcodes_next_total = list(filter(lambda x: x.find("nop(")!=-1,next_block))
    split_opcode = opcodes_next_total[0]
    opcodes_next = opcodes_next_total[1:]
    stop = False
    while(not stop and i <len(opcodes_next)):
        op = opcodes_next[i]
        if op != "nop(POP)":
          stop = True
        else:
          i+=1

    if i == 0:
        return tstack,[]
    else:
        if split_opcode == "nop(SSTORE)" or split_opcode == "nop(MSTORE)":
            split_stack = target_stack[:2]
            rest_stack = target_stack[2:]
            finished = False
            init_i = i
            while(i>0 and rest_stack !=[] and not finished):
                val = rest_stack.pop(0)

                if val in source_stack and val not in split_stack:
                    finished = True
                    rest_stack = [val]+rest_stack
                else:
                    i-=1

            todelete= True
            source_copy = list(source_stack)
            while i > 0 and todelete and (source_copy != []) and (rest_stack !=[]):
                val1 = rest_stack.pop(0)
                val2 = source_copy.pop(0)
                if val1 == val2:
                    i-=1
                else:
                    todelete = False
          
            pops2remove = init_i-i


            new_next_block,new_next_stack = modify_next_block(next_block,pops2remove)

            
            end_target_stack = tstack[:2]+tstack[2+pops2remove:]#split_stack+rest_stack

            return end_target_stack,(new_next_block,new_next_stack,pops2remove)
        else:
          return tstack,[]


def modify_next_block(next_block,pops2remove):
    split_instr = next_block[0]

    name = split_instr.split("(")[0]

    idx1 = int(split_instr.split(",")[0][9:-1]) #sstore(
    idx2 = int(split_instr.split(",")[1][2:-2])

    new_name = name+"(s("+str(idx1-pops2remove)+"),s("+str(idx2-pops2remove)+"))"

    new_nextblock = [new_name,next_block[1]]+next_block[2+pops2remove*2:]
    return new_nextblock,idx2-pops2remove
    
    
def translate_last_subblock(rule,block,sstack,sstack_idx,idx,isolated,preffix,simp, prev_pops):
    global max_instr_size
    global max_stack_size
    global num_pops
    global compute_gast
    
    init_globals()
    
    if not isolated:
        if "nop(JUMPI)" in block:
            guards_op = get_jumpi_opcodes(rule)

            num_guard = get_numguard_variables(guards_op)
        else:
            guards_op = []
            num_guard = 0
    else:
        num_guard = 0
        guards_op = []
        
    rbr_ins_aux = list(filter(lambda x: x.find("nop(")==-1, block))
    instructions = list(filter(lambda x: x!="" and x.find("skip")==-1, rbr_ins_aux))

    
    opcodes = list(filter(lambda x: x.find("nop(")!=-1,block))
    max_instr_size = compute_max_program_len(opcodes, num_guard)
    if opcodes != []:

        pops = list(filter(lambda x: x.find("nop(POP)")!=-1,opcodes))
        num_pops = len(pops)
        
        if not isolated:

            x = list(filter(lambda x: (x.find("POP")==-1) and (x.find("JUMPDEST")==-1) and (x.find("JUMP")==-1)and(x.find("JUMPI")==-1),opcodes))

            if x == [] and num_pops >0:
                t_vars_idx = sstack_idx-num_pops+1
                if t_vars_idx == sstack_idx and num_pops>0:
                    t_vars_idx-=1
                seq = range(0,t_vars_idx)
                tstack = list(map(lambda x: "s("+str(x)+")",seq))[::-1]
                
            else:
                
                tstack = generate_vars_target_stack(num_guard,instructions[-1],opcodes)[::-1]
        else:
            
            tstack = generate_target_stack_idx(len(sstack),opcodes)[::-1]
        get_s_counter(sstack,tstack)
        generate_encoding(instructions,tstack,sstack,simp)
    
        build_userdef_instructions()
        gas = get_block_cost(opcodes,len(guards_op))
        max_stack_size = max_idx_used(instructions,tstack)
        if gas!=0 and not is_identity_map(sstack,tstack):
            compute_gast = True
            new_opcodes = compute_opcodes2write(opcodes,num_guard)
            if not simp:
                index, fin = find_sublist(block,new_opcodes)
                init_info = get_encoding_init_block(block[index:fin+1],sstack)
            else:
                init_info = {}

            if prev_pops!=0:
                gas+=2*prev_pops
                
            generate_json(preffix+rule.get_rule_name(),sstack,tstack,sstack_idx,gas,init_info,subblock=idx,simplification = simp)
            if simp:
                write_instruction_block(rule.get_rule_name(),new_opcodes,subblock=idx)
    
def get_new_source_stack(instr,nop_instr,idx):
    
    if instr.find("=")!=-1:
        ins = instr.strip()
        var = ins.split("=")[0].strip()
        var_idx = int(var[2:-1])
        seq = range(var_idx,-1,-1)
        return (list(map(lambda x: "s("+str(x)+")",seq)),var_idx)

    else:

        bytecode = nop_instr.strip()[4:-1]
        bytecode_info = opcodes.get_opcode(bytecode)
        delta = bytecode_info[1]

        new_idx = idx-delta
        seq = range(new_idx,-1,-1)
        return (list(map(lambda x: "s("+str(x)+")",seq)),new_idx)
        
def compute_target_stack_subblock(instr, nop):
    bytecode = nop.strip()[4:-1]

    bytecode_info = opcodes.get_opcode(bytecode)
    alpha = bytecode_info[1]
    delta = bytecode_info[2]

    total = alpha - delta
    
    if instr.find("=")!=-1:
        vars_instr = instr.split("=")
        var = vars_instr[0].strip()

        idx_var = int(var[2:-1])

        idx_tstack = idx_var+total

    else:
        instr_aux = instr.strip()
        pos_open_br = instr_aux.find("(")


        variables = instr_aux[pos_open_br+1:-1].split(",")
        vars_aux = list(map(lambda x: int(x[2:-1]), variables))
        idx_tstack = max(vars_aux)

    return idx_tstack


def get_block_cost(opcodes_list,opcodes_guard):
    real_opcodes_aux = list(map(lambda x: x.strip()[4:-1],opcodes_list))
   
    if "JUMPDEST" in real_opcodes_aux:
        real_opcodes_aux.pop(0)

    if "JUMPI" in real_opcodes_aux:
        idx = -1-opcodes_guard
        real_opcodes = real_opcodes_aux[:idx]
    elif "JUMP" in real_opcodes_aux:
        real_opcodes = real_opcodes_aux[:-1]
    else:
        real_opcodes = real_opcodes_aux
   
    val = 0
    for op in real_opcodes:
        if op == "MULMOD":
            gas = 10
        else:
            gas = opcodes.get_ins_cost(op.strip())
        val+=gas
    return val

def get_cost(opcodes_list):
    real_opcodes_aux = list(map(lambda x: x.strip()[4:-1],opcodes_list))

    real_opcodes = real_opcodes_aux
    val = 0
    for op in real_opcodes:
        if op == "MULMOD" or op == "ADDMOD":
            gas = 10
        else:
            gas = opcodes.get_ins_cost(op.strip())
        val+=gas
    return val



def split_terminal_block(rule):
    blocks = []
    
    ins_block = []

    instructions = rule.get_instructions()
    
    for ins in instructions:
        ins_block.append(ins)
        if ins.startswith("nop("):
            nop = ins[4:-1]
            
            if nop in split_block+terminate_block:
                prev = ins_block[-2]
                blocks.append(ins_block)
                ins_block = [prev,ins]

    blocks.append(ins_block)
    
    return blocks

def generate_terminal_subblocks(rule,list_subblocks):
    global gas_t
    
    source_stack_idx = get_stack_variables(rule)
    source_stack = generate_source_stack_variables(source_stack_idx)

    source_stack_idx-=1
    i = 0

    pops2remove = 0
    while(i < len(list_subblocks)-1):
        init_globals()
        block = list_subblocks[i]
        
        nop_instr = block[-1]
        last_instr = block[-2]
        ts_idx = compute_target_stack_subblock(last_instr,nop_instr)
        
        seq = range(ts_idx,-1,-1)
        target_stack = list(map(lambda x: "s("+str(x)+")",seq))
        

        new_nexts,pops2remove = translate_subblock(rule,block,source_stack,target_stack,source_stack_idx,i,list_subblocks[i+1], pops2remove)

        if new_nexts == []:

            source_stack, source_stack_idx = get_new_source_stack(last_instr,nop_instr,ts_idx)
        else:
            new_block = new_nexts[0]
            new_idxstack= new_nexts[1] # it is the index of the last argument of sstore
            list_subblocks[i+1] = new_block
            source_stack_idx = new_idxstack
            seq = range(source_stack_idx-1,-1,-1)
            source_stack = list(map(lambda x: "s("+str(x)+")",seq))

        i+=1
    if compute_gast:
        gas_t+=get_cost(original_opcodes)
        
def translate_terminal_block(rule):
    blocks = split_terminal_block(rule)
    generate_terminal_subblocks(rule,blocks)

        
def write_instruction_block(rule_name,opcodes,subblock = None):
    if subblock != None:
        block_nm = rule_name+"."+str(subblock)
    else:
        block_nm = rule_name

    op = list(map(lambda x: x[4:-1],opcodes))
    
    if "disasms" not in os.listdir(gasol_path):
        os.mkdir(gasol_path+"/disasms")
    
    byte_file =  open(gasol_path+"/disasms/"+source_name+"_"+cname+"_"+block_nm+".disasm","w")
    for e in op:
        byte_file.write(e+"\n")
    byte_file.close()

def get_bytecode_representation(instructions):
    str_b = ""
    for i in instructions:
        i_aux = i.split()[0]
        c = opcodes.get_opcode(i_aux)
        # print c
        hex_val = str(c[0])
        if hex_val.startswith("0x"):
            op_val = hex_val[2:]
               
        else:
            op_val = hex(int(hex_val))[2:]

            if (int(op_val,16)<12):
                op_val = "0"+str(op_val)

        if i.startswith("PUSH"):
            num = i.split()[1][2:]
        else:
            num = ""
        str_b = str_b+op_val+num

def max_idx_used(instructions,tstack):
    ##print (instructions)
    
    if instructions == []:
        return 0
    
    if instructions[-1].find("call(")!=-1:
        idxs_call = list(map(lambda x: int(x[2:-1]),tstack))
    else:
        idxs_call = [0]

        
    insts = list(filter(lambda x: x.find("=")!=-1,instructions))
    ##print (insts)
    variables = list(map(lambda x: x.split("=")[0].strip(),insts))

    real_variables = list(filter(lambda x: x.find("s(")!=-1,variables))
    idxs = list(map(lambda x: int(x[2:-1]),real_variables))

    if idxs == []:
        idxs = [0]
    
    try:
        max_call = max(idxs_call)
        max_body = max(idxs)
        max_number = max(max_call,max_body)+1
    except:
        max_number = 0
    return max_number


def compute_max_program_len(opcodes, num_guard,block = None):
    if "nop(JUMPDEST)" in opcodes:
        new_opcodes_aux = opcodes[1:]
    else:
        new_opcodes_aux = opcodes

    if "nop(JUMPI)" in new_opcodes_aux:
        new_opcodes = new_opcodes_aux[:-1-num_guard]
    elif "nop(JUMP)" in new_opcodes_aux:
        new_opcodes = new_opcodes_aux[:-1]

    else:
        new_opcodes = new_opcodes_aux

    return len(new_opcodes)
    

def smt_translate_block(rule,name,preffix,simplification=True):
    global s_counter
    global max_instr_size
    global int_not0
    global source_name
    global blocks_json_dict
    global sfs_contracts
    
    init_globals()
    sfs_contracts = {}
    

    add_storage2split()
    
    blocks_json_dict = {}
    
    info_deploy = []

    source_name =  name
    
    int_not0 = [-1+2**256]#map(lambda x: -1+2**x, range(8,264,8))

    
    begin = dtimer()
    
    instructions = filter_opcodes(rule)
    
    opcodes = get_opcodes(rule)

    info = "INFO DEPLOY "+gasol_path+"ethir_OK_"+source_name+"_blocks_"+rule.get_rule_name()+" LENGTH="+str(len(opcodes))+" PUSH="+str(len(list(filter(lambda x: x.find("nop(PUSH")!=-1,opcodes))))
    info_deploy.append(info)
    

    res = is_optimizable(opcodes,instructions)
    if res:
        translate_block(rule,instructions,opcodes,True,preffix,simplification)

    else: #we need to split the blocks into subblocks
        r = False
        new_instructions = []

        subblocks = split_blocks(rule,r,new_instructions)
        generate_subblocks(rule,subblocks,True,preffix,simplification)

    end = dtimer()
    # for f in info_deploy:
    #     print f
    sfs_contracts["syrup_contract"] = blocks_json_dict
    end = dtimer()

    print("RULES  : "+str(gas_saved_op))
    #print("Blocks Generation SYRUP: "+str(end-begin)+"s")

def apply_transform(instr):
    global discount_op
    global saved_push
    global gas_saved_op
    
    opcode = instr["disasm"]
    if opcode == "AND":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=3
            
            discount_op+=1
            return 0
        elif inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[0]
    
        elif inp_vars[0] in int_not0 or inp_vars[1] in int_not0:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[1] if (inp_vars[0] in int_not0) else inp_vars[0]
        else:
            return -1
        
    elif opcode == "OR":
        inp_vars = instr["inpt_sk"]
        ##print (inp_vars)
        if 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]
        elif inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[0]
        else:
            return -1

    elif opcode == "XOR":
        inp_vars = instr["inpt_sk"]
        
        if inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            return 0
        elif 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]
        else:
            return -1

    elif opcode == "EXP":
        inp_vars = instr["inpt_sk"]
        
        if inp_vars[1] == 0:
            saved_push+=2
            gas_saved_op+=60

            discount_op+=1
            return 1
        elif inp_vars[1] == 1:
            saved_push+=1
            gas_saved_op+=60
            
            discount_op+=1
            return inp_vars[0]
        elif inp_vars[0] == 1:
            gas_saved_op+=60
            
            discount_op+=1
            return inp_vars[1]
        else:
            return -1

    elif opcode == "ADD":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[1] if inp_vars[0] == 0 else inp_vars[0]
        else:
            return -1

    elif opcode == "SUB":
        inp_vars = instr["inpt_sk"]
        if 0 == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            return inp_vars[0]
        elif inp_vars[0] == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=3

            discount_op+=1
            return 0
        else:
            return -1
        
    elif opcode == "MUL":
        inp_vars = instr["inpt_sk"]
        if 0 in inp_vars:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            return 0
        elif 1 in inp_vars:
            saved_push+=1
            gas_saved_op+=5
            
            discount_op+=1
            return inp_vars[1] if inp_vars[0] == 1 else inp_vars[0]
        else:
            return -1

    elif opcode == "DIV":
        inp_vars = instr["inpt_sk"]
        if  1 == inp_vars[1]:
            saved_push+=1
            gas_saved_op+=5
            
            discount_op+=1
            return inp_vars[0]

        elif inp_vars == 0:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            return 0

        else:
            return -1

    elif opcode == "MOD":
        inp_vars = instr["inpt_sk"]
        if  1 == inp_vars[1]:
            saved_push+=2
            gas_saved_op+=5
            
            discount_op+=1
            return 0

        elif inp_vars[0] == inp_vars[1]:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            return 0

        elif inp_vars[1] == 0:
            saved_push+=2
            gas_saved_op+=5

            discount_op+=1
            return 0

            
        else:
            return -1

    elif opcode == "EQ":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == inp_vars[1]:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3
            
            return 1
        else:
            return -1

    elif opcode == "GT" or opcode == "SGT":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == 0:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            return 0
        elif inp_vars[0] == inp_vars[1]:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3
            
            return 0
        else:
            return -1

    elif opcode == "LT" or opcode == "SLT":
        inp_vars = instr["inpt_sk"]
        if inp_vars[1] == 0:
            saved_push+=2
            gas_saved_op+=3

            discount_op+=1
            return 0
        elif inp_vars[0] == inp_vars[1]:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3
            
            return 0
        else:
            return -1

    elif opcode == "NOT":
        inp_vars = instr["inpt_sk"]
        r, val = all_integers(inp_vars)
        if r:
            val_end = ~(int(val[0]))+2**256

            saved_push+=1
            gas_saved_op+=3

            return val_end
        else:
            return -1
        
    elif opcode == "ISZERO":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == 0:
            gas_saved_op+=3
            saved_push+=1
            return 1
        elif inp_vars[0] == 1:
            gas_saved_op+=3
            saved_push+=1
            return 0
        else:
            return -1

    elif opcode == "SHR" or opcode == "SHL":
        inp_vars = instr["inpt_sk"]
        if inp_vars[0] == 0:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3
            return inp_vars[1]
        elif inp_vars[1] == 0:
            discount_op+=1
            saved_push+=2
            gas_saved_op+=3
            return inp_vars[0]
        else:
            return -1


def apply_all_simp_rules(user_def,list_vars,tstack):
    modified = True
    user_def_instrs = user_def
    target_stack = tstack
    while(modified):
        ##print ("CUCU")
        modified, user_def_instrs,target_stack = apply_transform_rules(user_def_instrs,list_vars,target_stack)
    return user_def_instrs,target_stack

def apply_transform_rules(user_def_instrs,list_vars,tstack):
    to_delete = []
    target_stack = tstack
    modified = False
    for instr in user_def_instrs:

        if instr["disasm"] in ["AND","OR","XOR","ADD","SUB","MUL","DIV","EXP","EQ","GT","LT","NOT","ISZERO"]:
            r = apply_transform(instr)

            if r!=-1:
                print("[RULE]: Simplification rule type 1: "+str(instr))
                
                replace_var_userdef(instr["outpt_sk"][0],r,user_def_instrs)
                target_stack = replace_var(instr["outpt_sk"][0],r,target_stack)
                delete_from_listvars(instr["outpt_sk"][0],list_vars)
                to_delete.append(instr)
                modified = True
    i = 0
    new_user_def = []
    while len(user_def_instrs)>0:
        instr = user_def_instrs.pop()
        if instr not in to_delete:
            new_user_def.append(instr)


    return modified, new_user_def, target_stack, 

def replace_var_userdef(out_var,value,user_def):
    modified_instrs = []
    for instr in user_def:
        inpt = instr["inpt_sk"]
        if out_var in inpt:
            idx = inpt.index(out_var)
            part1 = inpt[:idx]
            part2 = inpt[idx+1:]
            part1.append(value)
            new_inpt = part1+part2
            instr["inpt_sk"] = new_inpt
            
def replace_var(out_var,value,tstack):
    new_stack = []
    if out_var in tstack:
        for s in tstack:
            if s!= out_var:
                new_stack.append(s)
            else:
                new_stack.append(value)
        return new_stack
    else:
        return tstack

def delete_from_listvars(out_var,list_vars):
    idx = list_vars.index(out_var)
    list_vars.pop(idx)


def check_rule_iszero_gt(num_gt,num_iszero):
    for gt in num_gt:
        o_var = gt["outpt_sk"]
        


def apply_cond_transformation(instr,user_def_instrs,tstack):
    global discount_op
    global saved_push
    global gas_saved_op
    global user_def_counter

    
    opcode = instr["disasm"]
    
    if opcode == "GT" or opcode == "SGT":
        if 0 == instr["inpt_sk"][1]:
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero) == 1:
                index = user_def_instrs.index(is_zero[0])
                zero_instr = user_def_instrs[index]
                zero_instr["inpt_sk"] = [instr["inpt_sk"][0]]
                saved_push+=2
                gas_saved_op+=3

                discount_op+=2

                #print("ISZ(GT(X,0))")
                return True, [instr]
            else:
                return False, []

        elif 1 == instr["inpt_sk"][0]:
            var = instr["inpt_sk"][1]
            idx = user_def_counter.get("ISZERO",0)
            instr["id"] = "ISZERO_"+str(idx)
            instr["opcode"] = "15"
            instr["disasm"] = "ISZERO"
            instr["inpt_sk"] = [var]
            instr["commutative"] = False
            discount_op+=1
            saved_push+=2

            user_def_counter["ISZERO"]=idx+1
            
            #print("GT(1,X)")
            return True, []


        else:
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
                if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:
                    # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                    old_var = instr["outpt_sk"]
                    new_var = zero2[0]["outpt_sk"]
                    instr["outpt_sk"] = new_var
                    
                    discount_op+=2

                    gas_saved_op+=6

                    #print("ISZ(ISZ(GT(X,Y)))")

                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []

    elif opcode == "ISZERO":
    
        out_var = instr["outpt_sk"][0]
        is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))

        is_eq = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "EQ",user_def_instrs))
        
        if len(is_zero)==1:
         
            zero = is_zero[0]
  
            zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:
             
                # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                old_var = instr["outpt_sk"]
                new_var = zero2[0]["outpt_sk"]
                instr["outpt_sk"] = new_var

                discount_op+=2
                
                gas_saved_op+=6

                #print("ISZ(ISZ(ISZ(X)))")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [zero,zero2[0]]
            else:
                return False, []

        elif len(is_eq) == 1:
            eq = is_eq[0]

            if 1 in eq["inpt_sk"]:
                old_var = instr["outpt_sk"]
                new_var = eq["outpt_sk"]
                # instr["outpt_sk"] = eq["outpt_sk"]
                instr["outpt_sk"] = new_var
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                #print("EQ(1,ISZ(X))")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [eq]

            else:
                return False, []
        else:
                
            return False, []
            
    elif opcode == "LT" or opcode == "SLT":
         if 0 == instr["inpt_sk"][0]:
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero) == 1:
                index = user_def_instrs.index(is_zero[0])
                zero_instr = user_def_instrs[index]
                zero_instr["inpt_sk"] = [instr["inpt_sk"][1]]
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                #print("ISZ(LT(0,X))")
                
                return True, [instr]
            else:
                return False, []

         elif 1 == instr["inpt_sk"][1]:
            var = instr["inpt_sk"][0]
            idx = user_def_counter.get("ISZERO",0)
            instr["id"] = "ISZERO_"+str(idx)
            instr["opcode"] = "15"
            instr["disasm"] = "ISZERO"
            instr["inpt_sk"] = [var]
            instr["commutative"] = False
            discount_op+=1

            saved_push+=1

            user_def_counter["ISZERO"]=idx+1
            
            #print("LT(X,1)")
            return True, []
        
         else:
            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
                if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:
                    old_var = instr["outpt_sk"]
                    new_var = zero2[0]["outpt_sk"]
                    instr["outpt_sk"] = new_var

                    # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                    discount_op+=2

                    gas_saved_op+=6

                    #print("ISZ(ISZ(LT(X,Y)))")

                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []
            
    elif opcode == "EQ":
        if 0 in instr["inpt_sk"]:
            var0 = instr["inpt_sk"][0]
            var1 = instr["inpt_sk"][1]

            nonz = var1 if var0 == 0 else var0
            idx = user_def_counter.get("ISZERO",0)
            instr["id"] = "ISZERO_"+str(idx)
            instr["opcode"] = "15"
            instr["disasm"] = "ISZERO"
            instr["inpt_sk"] = [nonz]
            instr["commutative"] = False

            discount_op+=1
            saved_push+=1

            #print("EQ(0,X)")

            user_def_counter["ISZERO"]=idx+1
            
            return True, []

        else:

            out_var = instr["outpt_sk"][0]
            is_zero = list(filter(lambda x: out_var in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
            if len(is_zero)==1:
                zero = is_zero[0]
                zero2 = list(filter(lambda x: zero["outpt_sk"][0] in x["inpt_sk"] and x["disasm"] == "ISZERO",user_def_instrs))
                if len(zero2) == 1 and zero["outpt_sk"][0] not in tstack:

                    old_var = instr["outpt_sk"]
                    new_var = zero2[0]["outpt_sk"]
                    instr["outpt_sk"] = new_var
                    # instr["outpt_sk"] = zero2[0]["outpt_sk"]
                    discount_op+=2

                    gas_saved_op+=6


                    #print("ISZ(ISZ(EQ(X,Y)))")

                    update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                    
                    return True, [zero,zero2[0]]
                else:
                    return False, []
            else:
                
                return False, []
            
    
    elif opcode == "AND":
        out_pt = instr["outpt_sk"][0]
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        or_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "OR", user_def_instrs))
        
        if len(and_op)==1:
            and_instr = and_op[0]
            if (and_instr["inpt_sk"][1] in instr["inpt_sk"]) or (and_instr["inpt_sk"][0] in instr["inpt_sk"]):
                # #print(user_def_instrs)
                # #print("***************")
                
                old_var = instr["outpt_sk"]
                new_var = and_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                # instr["outpt_sk"] = and_instr["outpt_sk"]
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                #print("AND(X,AND(X,Y))")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [and_instr]
            else:
                return False, []

        elif len(or_op) == 1:
            or_instr = or_op[0]
            out_pt2 = or_instr["outpt_sk"][0]
            if out_pt == or_instr["inpt_sk"][1]: #(or(x,and(x,y)) = x, or(x,and(y,x)) = x, or(and(x,y),x) = x, or(and(y,x),x) = x
    
                if or_instr["inpt_sk"][0] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif or_instr["inpt_sk"][0] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []
            elif out_pt == or_instr["inpt_sk"][0]:
                if or_instr["inpt_sk"][1] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif or_instr["inpt_sk"][1] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []

            else:
                return False, []

            i = 0
                
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = x

            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = x
                    
            discount_op+=2
            gas_saved_op+=6


            #print("OR(X,AND(X,Y))")
            
            return True, [or_instr,instr]
            

        else:
            return False,[]
        
    elif opcode == "OR":
        out_pt = instr["outpt_sk"][0]
        or_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "OR", user_def_instrs))
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        if len(or_op)==1:
            or_instr = or_op[0]
            if (or_instr["inpt_sk"][1] in instr["inpt_sk"]) or (or_instr["inpt_sk"][0] in instr["inpt_sk"]):
                instr["outpt_sk"] = or_instr["outpt_sk"]
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                #print("OR(OR(X,Y),Y)")
                
                return True, [or_instr]
            else:
                return False, []

        elif len(and_op) == 1: 
            and_instr = and_op[0]
            out_pt2 = and_instr["outpt_sk"][0]
            if out_pt == and_instr["inpt_sk"][1]: #(and(x,or(x,y)) = x, and(x,or(y,x)) = x, and(or(x,y),x) = x, and(or(y,x),x) = x
    
                if and_instr["inpt_sk"][0] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif and_instr["inpt_sk"][0] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []
            elif out_pt == and_instr["inpt_sk"][0]:
                if and_instr["inpt_sk"][1] == instr["inpt_sk"][0]:
                    x = instr["inpt_sk"][0]
                elif and_instr["inpt_sk"][1] == instr["inpt_sk"][1]:
                    x = instr["inpt_sk"][1]
                else:
                    return False, []

            else:
                return False, []

            i = 0
                
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = x

            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = x
                    
            discount_op+=2
            gas_saved_op+=6

            #print("AND(X,OR(X,Y))")
            
            return True, [and_instr,instr]
            
        else:
            return False,[]


    elif opcode == "XOR":
        out_pt = instr["outpt_sk"][0]
        xor_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "XOR", user_def_instrs))
        isz_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "ISZERO", user_def_instrs))
        
        if len(xor_op)==1:
            xor_instr = xor_op[0]
            out_pt2 = xor_instr["outpt_sk"][0]
            if out_pt == xor_instr["inpt_sk"][1]: #xor(x,xor(x,y)) = y, xor(x,xor(y,x)) = y, xor(xor(x,y),x) = y, xor(xor(y,x),x) = y
    
                if xor_instr["inpt_sk"][0] == instr["inpt_sk"][0]:
                    y = instr["inpt_sk"][1]
                elif xor_instr["inpt_sk"][0] == instr["inpt_sk"][1]:
                    y = instr["inpt_sk"][0]
                else:
                    return False, []
            elif out_pt == xor_instr["inpt_sk"][0]:
                if xor_instr["inpt_sk"][1] == instr["inpt_sk"][0]:
                    y = instr["inpt_sk"][1]
                elif xor_instr["inpt_sk"][1] == instr["inpt_sk"][1]:
                    y = instr["inpt_sk"][0]
                else:
                    return False, []

            else:
                return False, []

            i = 0
                
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = y

            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = y
                    
            discount_op+=2
            gas_saved_op+=6

            #print("XOR(X,XOR(X,Y))")
            
            return True, [xor_instr,instr]

        elif len(isz_op) == 1: #ISZ(XOR(X,Y)) = EQ(X,Y)
            isz_instr = isz_op[0]
            idx = user_def_counter.get("EQ",0)
            
            instr["outpt_sk"] = isz_instr["outpt_sk"]
            instr["id"] = "EQ_"+str(idx)
            instr["opcode"] = "14"
            instr["disasm"] = "EQ"
            instr["commutative"] = True            

            discount_op+=1
            gas_saved_op+=3

            user_def_counter["EQ"]=idx+1
            #print("ISZ(XOR(X,Y))")
            
            return True, [isz_instr]
                
        else:
            return False,[]

        
    elif opcode == "NOT":
        out_pt = instr["outpt_sk"][0]
        not_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "NOT", user_def_instrs))
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        or_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "NOT", user_def_instrs))

        if len(not_op)==1:
            not_instr = not_op[0]
            out_pt2 = not_instr["outpt_sk"][0]
            real_var = instr["inpt_sk"]

            i = 0
            while (i<len(tstack)):
                if tstack[i] == (out_pt2):
                    tstack[i] = real_var

            for elems in user_def_instrs:
                if out_pt2 in elems["inpt_sk"]:
                    pos = elems["inpt_sk"].index(out_pt2)
                    elems["inpt_sk"][pos] = real_var
                    
                discount_op+=2
                gas_saved_op+=6

                #print("NOT(NOT(X))")
                
                return True, [not_instr,instr]
            else:
                return False, []

        elif len(and_op) == 1: #and(x,not(x)) = 0
            and_instr = and_op[0]
            out_pt2 = and_instr["outpt_sk"][0]

            if instr["inpt_sk"][0] in and_instr["inpt_sk"]:
                real_var = 0
                i = 0
                while (i<len(tstack)):
                    if tstack[i] == (out_pt2):
                        tstack[i] = real_var

                for elems in user_def_instrs:
                    if out_pt2 in elems["inpt_sk"]:
                        pos = elems["inpt_sk"].index(out_pt2)
                        elems["inpt_sk"][pos] = real_var
                    
                discount_op+=2
                gas_saved_op+=6

                #print("AND(X,NOT(X))")
                
                return True, [and_instr,instr]

            else:
                return False, []

        elif len(or_op) == 1: #or(x,not(x)) = 2^256-1
            or_instr = or_op[0]
            out_pt2 = or_instr["outpt_sk"][0]

            if instr["inpt_sk"][0] in or_instr["inpt_sk"]:
                real_var = -1+2**256
                i = 0
                while (i<len(tstack)):
                    if tstack[i] == (out_pt2):
                        tstack[i] = real_var

                for elems in user_def_instrs:
                    if out_pt2 in elems["inpt_sk"]:
                        pos = elems["inpt_sk"].index(out_pt2)
                        elems["inpt_sk"][pos] = real_var
                    
                discount_op+=2
                gas_saved_op+=6

                #print("OR(X,NOT(X))")
                
                return True, [or_instr,instr]

        else:
            return False,[]


    elif opcode == "ORIGIN" or opcode == "COINBASE" or opcode == "CALLER":
        out_pt = instr["outpt_sk"][0]
        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))
        if len(and_op) == 1:
            and_instr = and_op[0]
            if -1+2**160 in and_instr["inpt_sk"]:
                #print(user_def_instrs)
                #print(instr)
                #print(and_instr)
                #print(-1+2**160)

                old_var = instr["outpt_sk"]
                new_var = and_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                #print("AND(ORIGIN,2^160-1)")

                # #print("PREVIOUS")
                # #print(old_var)
                # #print(new_var)
                # #print(tstack)
                # #print(user_def_instrs)
                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                # #print("AFTER")
                # #print(tstack)
                # #print(tstack)
                # #print(user_def_instrs)
                
                return True,[and_instr]
            else:
                return False, []
        else:
            return False, []


    elif opcode == "SUB":
        out_pt = instr["outpt_sk"][0]
        isz_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "ISZERO", user_def_instrs))
        

        if len(isz_op) == 1: #ISZ(SUB(X,Y)) = EQ(X,Y)
            isz_instr = isz_op[0]
            idx = user_def_counter.get("EQ",0)
            
            old_var = instr["outpt_sk"]
            new_var = isz_instr["outpt_sk"]
            instr["outpt_sk"] = new_var
            
            # instr["outpt_sk"] = isz_instr["outpt_sk"]
            instr["id"] = "EQ_"+str(idx)
            instr["opcode"] = "14"
            instr["disasm"] = "EQ"
            instr["commutative"] = True            

            discount_op+=1
            gas_saved_op+=3

            user_def_counter["EQ"]=idx+1
            #print("ISZ(SUB(X,Y))")

            update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
            
            return True, [isz_instr]
                
        else:
            return False,[]

    elif opcode == "SHL":
        out_pt = instr["outpt_sk"][0]
        mul_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "MUL", user_def_instrs))
        div_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "DIV", user_def_instrs))
        if len(mul_op) == 1 and instr["inpt_sk"][1] == 1:
            mul_instr = mul_op[0]

            if mul_instr["inpt_sk"][1] == out_pt:
                old_var = instr["outpt_sk"]
                new_var = mul_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                instr["inpt_sk"][1] = mul_instr["inpt_sk"][0]

                discount_op+=1
                gas_saved_op+=5
                saved_push+=1

                #print("MUL(X,SHL(Y,1)")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [mul_instr]

            elif mul_instr["inpt_sk"][0] == out_pt:
                # instr["outpt_sk"] = mul_instr["outpt_sk"]
                old_var = instr["outpt_sk"]
                new_var = mul_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                instr["inpt_sk"][1] = mul_instr["inpt_sk"][1]

                discount_op+=1
                gas_saved_op+=5
                saved_push+=1

                #print("MUL(SHL(X,1),Y)")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [mul_instr]

            else:
                return False, []

        elif len(div_op) == 1 and instr["inpt_sk"][1] == 1:
            div_instr = div_op[0]

            if div_instr["inpt_sk"][1] == out_pt:
                old_var = instr["outpt_sk"]
                new_var = div_instr["outpt_sk"]
                instr["outpt_sk"] = new_var
                # instr["outpt_sk"] = div_instr["outpt_sk"]
                instr["inpt_sk"][1] = div_instr["inpt_sk"][0]

                idx = user_def_counter.get("SHR",0)
            
                instr["id"] = "SHR_"+str(idx)
                instr["opcode"] = "1c"
                instr["disasm"] = "SHR"
                instr["commutative"] = False            
                
                
                discount_op+=1
                gas_saved_op+=5
                saved_push+=1

                user_def_counter["SHR"]=idx+1
                #print("DIV(X,SHL(Y,1))")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True, [div_instr]
            
        else:
            return False, []

    elif opcode == "ADDRESS":
        out_pt = instr["outpt_sk"][0]
        bal_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "BALANCE", user_def_instrs))

        and_op = list(filter(lambda x: out_pt in x["inpt_sk"] and x["disasm"] == "AND", user_def_instrs))

        if len(bal_op) == 1:
            bal_instr = bal_op[0]

            old_var = instr["outpt_sk"]
            new_var = bal_instr["outpt_sk"]
            instr["outpt_sk"] = new_var
            
            # instr["outpt_sk"] = bal_instr["outpt_sk"]

            idx = user_def_counter.get("SELFBALANCE",0)
            
            instr["id"] = "SELFBALANCE_"+str(idx)
            instr["opcode"] = "47"
            instr["disasm"] = "SELFBALANCE"
            instr["commutative"] = False            
                
            discount_op+=1
            gas_saved_op+=397 #BALANCE 400 ADDRESS 2 SELFBALANCE 5

            user_def_counter["SELFBALANCE"]=idx+1
            #print("BALANCE(ADDRESS)")

            update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
            
            return True,[bal_instr]
        
        elif len(and_op) == 1:
            and_instr = and_op[0]
            if -1+2**160 in and_instr["inpt_sk"]:
                # instr["outpt_sk"] = and_instr["outpt_sk"]
                old_var = instr["outpt_sk"]
                new_var = and_instr["outpt_sk"]
                instr["outpt_sk"] = new_var

                discount_op+=1

                saved_push+=1
                gas_saved_op+=3

                #print("AND(ADDRESS,2^160)")

                update_tstack_userdef(old_var[0], new_var[0],tstack, user_def_instrs)
                
                return True,[and_instr]
            else:
                return False, []
        else:
            return False, []
        
    elif opcode == "EXP":
        if instr["inpt_sk"][0] == 0:
            instr["inpt_sk"].pop(0)

            idx = user_def_counter.get("ISZERO",0)
            
            instr["id"] = "ISZERO_"+str(idx)
            instr["opcode"] = "15"
            instr["disasm"] = "ISZERO"
            instr["commutative"] = False            
                
            saved_push+=1
            gas_saved_op+=57

            user_def_counter["ISZERO"]=idx+1
            #print("EXP(0,X)")
            
            return True, []

        elif instr["inpt_sk"][0] == 2:
            instr["inpt_sk"].pop(0)
            instr["inpt_sk"].append(1)
            idx = user_def_counter.get("SHL",0)
            
            instr["id"] = "SHL_"+str(idx)
            instr["opcode"] = "1b"
            instr["disasm"] = "SHL"
            instr["commutative"] = False            
                
            gas_saved_op+=57 #EXP-SHL

            user_def_counter["SHL"]=idx+1
            #print("EXP(2,X)")
            return True, []

        else:
            return False, []

    else:
        return False, []


    
def apply_all_comparison(user_def_instrs,tstack):
    modified = True
    while(modified):
        ##print ("********************IT*********************")
        modified = apply_comparation_rules(user_def_instrs,tstack)

        
def apply_comparation_rules(user_def_instrs,tstack):
    modified = False

    for instr in user_def_instrs:
        
        r, d_instr = apply_cond_transformation(instr,user_def_instrs,tstack)

        if r:
            print("[RULE]: Simplification rule type 2: "+str(instr))
            # print("[RULE]: Delete rules: "+str(d_instr))
            modified = True
            for b in d_instr:
                idx = user_def_instrs.index(b)
                user_def_instrs.pop(idx)
    return modified
                   
def update_tstack_userdef(old_var, new_var,tstack, user_def_instrs):
    i = 0
    while(i<len(tstack)):
        if tstack[i] == old_var:
            tstack[i] = new_var
        i+=1

    for instr in user_def_instrs:
        inp_st = instr["inpt_sk"]
        if old_var in inp_st:
            i = inp_st.index(old_var)
            instr["inpt_sk"][i] = new_var
            
def get_sfs_dict():
    return sfs_contracts

def is_identity_map(source_stack,target_stack):

    if len(user_defins) > 0:
        return False
    
    if len(source_stack) != len(target_stack):
        return False

    
    for v in variable_content:
        if v != variable_content[v]:
            return False

    return True
