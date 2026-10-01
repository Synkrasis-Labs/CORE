"""Auditable corrections applied only by the versioned paper evaluator.

Original dataset remains intact for legacy score reproducibility. Repairs are
supported by source task prompts, references, and neighboring DFA structure.
"""
from copy import deepcopy


def repaired_record(record):
    r = deepcopy(record)
    notes = []
    pid = r['prompt_id']
    def require(condition):
        if not condition:
            raise ValueError(f'Dataset repair precondition changed for {pid}')
    def node(name):
        return next(n for n in r['nodes'] if n['name'] == name)
    if pid == 'crud_3':
        # G3 means Jane was updated first. B (John) must progress, not loop.
        loop = next(e for e in node('G3')['transitions'] if e['to']=='G3')
        require(loop['symbols'][-1] == 'B')
        loop['symbols'][-1] = "B'"
        notes.append('G3 repeat-update loop B -> B-prime; John update now progresses deterministically.')
    elif pid == 'desktop_manager_6':
        edge = node('G2')['transitions'][0]
        require(edge['from']=='G1' and edge['symbols']==["E'"])
        edge['from']='G2'
        notes.append('Corrected G2 outgoing edge source G1 -> G2.')
    elif pid == 'event_scheduler_4':
        loop=node('G1')['transitions'][1]
        require(loop['symbols']==['E', "F'"])
        loop['symbols']=['E','F']
        notes.append('Undefined F-prime self-loop -> declared time_until_event symbol F.')
    elif pid == 'file_management_5':
        loop=node('G2')['transitions'][0]
        require("KK'" in loop['symbols'])
        i=loop['symbols'].index("KK'")
        loop['symbols'][i:i+1]=['K', "K'"]
        notes.append('Split concatenated terminal read symbols KK-prime into K and K-prime.')
    elif pid == 'transactions_3':
        require(r['nodes'][-1]==r['nodes'][-2])
        r['nodes'].pop()
        loop=node('G5')['transitions'][1]
        require(loop['symbols']==["D'", "D''", 'F'])
        loop['symbols']=['D', "D''", 'F']
        notes.append('Removed duplicate G6; G5 reread loop D-prime -> D so B456 confirmation progresses.')
    elif pid == 'transactions_7':
        # Prompt/reference: create D001, deposit 1000, interest .1, withdraw 300.
        # Existing DFA is copied from a close-account task, so reconstruct these
        # four required progress edges explicitly rather than guessing aliases.
        require(r['alphabet']['B']['arguments']['amount']['value']==100)
        r['alphabet']['B']['arguments']['amount']['value']=1000
        r['alphabet']["B'"]['arguments']['amount']['excluded_values']=[1000]
        r['alphabet']['C']['arguments']['account_id']['value']='D001'
        r['alphabet']['C']['arguments']['amount']['value']=300
        r['nodes']=[{'name':f'G{i}', 'is_final':i==4, 'transitions':
            ([{'symbols':[symbol], 'from':f'G{i}', 'to':f'G{i+1}'}] if i<4 else [])+
            [{'symbols':['D', "D'", 'F'], 'from':f'G{i}', 'to':f'G{i}'}]}
            for i,symbol in enumerate(['A','B','G','C',None])]
        notes.append('Aligned copied close-account DFA and deposit amount with task/reference: A,B,G,C; 1000 deposit, 300 withdrawal.')
    return r, notes
