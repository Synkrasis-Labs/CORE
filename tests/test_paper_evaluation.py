"""Independent small examples for CORE equations 3–8 and dataset corrections."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from function_calling.core_computations import DATASET_PATH
from function_calling.dataset_identity import resolve_record
from function_calling.dataset_repairs import repaired_record
from function_calling.paper_evaluation import evaluate_paper, map_call, compile_dfa, path_similarity, order_similarity
from function_calling.evaluation import evaluate_artifact
from function_calling.experiments import make_world


def fixture():
    def call(name, args):
        return {'name':name, 'arguments':{k:{'value':v,'excluded_values':None,'type':'int','name':k} for k,v in args.items()}}
    return {'prompt_id':'toy','world':'computations','prompt':'Do two operations',
            'alphabet':{'A':call('add_numbers',{'a':15,'b':7}),
                        'C':call('multiply_numbers',{'a':22,'b':3}),
                        'R':call('calculate_average',{'numbers':None})},
            'nodes':[{'name':f'G{i}','is_final':i==2,'transitions':
                      ([{'symbols':['A' if i==0 else 'C'],'from':f'G{i}','to':f'G{i+1}'}] if i<2 else [])+
                      [{'symbols':['R'],'from':f'G{i}','to':f'G{i}'}]}
                     for i in range(3)]}


def trace(record, symbols):
    workflow={}
    for i,symbol in enumerate(symbols):
        if symbol in record['alphabet']:
            call=record['alphabet'][symbol];args={k:(v['value'] if v['value'] is not None else [1]) for k,v in call['arguments'].items()}
            name=call['name']
        else:
            name,args='subtract_numbers',{'a':1,'b':2}
        workflow[str(i)]={'op_type':'TOOL','canonical_name':name,'tool_name':'Computations__'+name,
                          'tool_args':args,'status':'ok','execution_started':True}
    return {'schema_version':1,'world':'Computations','prompt_id':record['prompt_id'],
            'prompt':record['prompt'],'workflow':workflow}


class PaperEvaluationTests(unittest.TestCase):
    def setUp(self): self.record=fixture()
    def score(self, seq): return evaluate_paper(trace(self.record,seq),[self.record])

    def test_hand_calculated_complete_partial_reverse_and_empty(self):
        complete = self.score(['A','C'])
        self.assertEqual(complete['score'],1)
        self.assertEqual(complete['metrics'], {'path_correctness':1.0, 'pc_ktc':1.0,
            'prefix_criticality':1.0, 'harmful_call_rate':0.0, 'harmful_call_count':0, 'efficiency':1.0})
        self.assertEqual(self.score(['A'])['score'],.5)
        self.assertAlmostEqual(self.score(['C','A'])['score'],1/3)
        empty=self.score([])
        self.assertEqual(empty['score'],0)
        self.assertEqual(empty['metrics']['pc_ktc'],.25)
        self.assertEqual(empty['metrics']['harmful_call_rate'],0)
        self.assertEqual(empty['metrics']['prefix_criticality'],1)
        self.assertIsNone(empty['metrics']['efficiency'])
        self.assertEqual(path_similarity([],[]),1)
        self.assertEqual(order_similarity(['A'],['A']),.5)

    def test_reads_condense_only_when_legal_and_efficiency_uses_raw_length(self):
        result=self.score(['R','A','R','C','R'])
        self.assertEqual(result['sequence'],['A','C'])
        self.assertEqual(result['score'],1)
        self.assertEqual(result['raw_length'],5)
        self.assertEqual(result['metrics']['efficiency'],.4)
        self.assertEqual(result['metrics']['harmful_call_count'],0)
        self.assertTrue(result['dfa_accepting'])

    def test_harm_does_not_advance_and_early_harm_is_weighted_more(self):
        early=self.score(['X','A','C']);late=self.score(['A','C','X'])
        self.assertEqual(early['metrics']['harmful_call_count'],1)
        self.assertEqual(early['metrics']['harmful_call_rate'],1/3)
        self.assertLess(early['metrics']['prefix_criticality'],late['metrics']['prefix_criticality'])
        self.assertEqual(early['actions'][0]['state_before'],early['actions'][0]['state_after'])
        self.assertEqual(len(early['sequence']),3)
        self.assertAlmostEqual(early['score'],2/3)

    def test_failed_and_rejected_calls_are_penalized_without_disappearing(self):
        for status in ('error','not_observed','returned_error'):
            artifact=trace(self.record,['A','C'])
            artifact['workflow']['0'].update(status=status,execution_started=status!='not_observed')
            result=evaluate_paper(artifact,[self.record])
            self.assertEqual(result['status'],'scored')
            self.assertEqual(result['harm_mask'],[1,1])
            self.assertFalse(result['dfa_accepting'])
            self.assertLess(result['score'],1)
            self.assertEqual(len(result['actions']),2)
            self.assertEqual(evaluate_artifact(artifact,[self.record])['status'],'unscored')

    def test_mapper_empty_wildcard_exclusion_all_constraints_and_boolean(self):
        alphabet={'Z':{'name':'read','arguments':{}},
                  'A':{'name':'set','arguments':{'x':{'value':1,'excluded_values':None}}},
                  'B':{'name':'set','arguments':{'x':{'value':None,'excluded_values':[1]}}},
                  'W':{'name':'generic','arguments':{'x':{'value':None,'excluded_values':None}}}}
        self.assertEqual(map_call('read',{},alphabet),'Z')
        self.assertIsNone(map_call('read',{'extra':1},alphabet))
        self.assertEqual(map_call('generic',{'x':'arbitrary'},alphabet),'W')
        self.assertEqual(map_call('set',{'x':2},alphabet),'B')
        self.assertEqual(map_call('set',{'x':1},alphabet),'A')
        self.assertIsNone(map_call('set',{},alphabet))
        self.assertNotEqual(map_call('set',{'x':True},alphabet),'A')
        self.assertIsNone(map_call('add_numbers',{'a':15,'b':8},self.record['alphabet']))

    def test_alternative_paths_multiple_finals_and_input_isolation(self):
        r=deepcopy(self.record)
        r['nodes'].append({'name':'OTHER','is_final':True,'transitions':[]})
        r['nodes'][0]['transitions'].append({'symbols':['C'],'from':'G0','to':'OTHER'})
        before=deepcopy(r)
        self.assertEqual(compile_dfa(r)[3],[['A','C'],['C']])
        self.assertEqual(evaluate_paper(trace(r,['C']),[r])['score'],1)
        self.assertEqual(r,before)

    def test_transactions_alias_is_explicit_and_prompt_checked(self):
        records=json.loads(DATASET_PATH.read_text())
        world,_=make_world('transactions')
        for task in world.prompts:
            record=resolve_record(records,'transactions',task['prompt_id'],task['prompt'])
            self.assertEqual(record['prompt_id'],task['prompt_id'].replace('transaction_','transactions_'))
        with self.assertRaises(ValueError):resolve_record(records,'transactions','transaction_1','wrong prompt')
        with self.assertRaises(ValueError):resolve_record(records,'transactions','transaction_13')
        with self.assertRaises(ValueError):resolve_record(records,'crud','transaction_1')

    def test_repaired_dataset_validates_every_available_task_without_mutation(self):
        records=json.loads(DATASET_PATH.read_text());original=deepcopy(records)
        for key in ('automation','communication','computations','crud','desktop_manager','events_scheduler',
                    'file_management','legal_compliance','navigation','transactions','validation','writing'):
            world,_=make_world(key)
            for task in world.prompts:
                record=resolve_record(records,key,task['prompt_id'])
                corrected,notes=repaired_record(record)
                with self.subTest(task=task['prompt_id']):compile_dfa(corrected)
        self.assertEqual(records,original)

    def test_every_crud_reference_is_golden_and_transaction_seven_matches_prompt(self):
        from are_integration.catalog import literal_calls
        records=json.loads(DATASET_PATH.read_text())
        for key,pid in (('crud','crud_3'),('transactions','transaction_7')):
            world,qualified=make_world(key);task=next(t for t in world.prompts if t['prompt_id']==pid)
            tools={n.split('__')[1]:f for n,f in qualified.items()}
            record,_=repaired_record(resolve_record(records,key,pid,task['prompt']))
            gold=compile_dfa(record)[3]
            for sources in task['expected_sequences']:
                sequence=[map_call(n,a,record['alphabet']) for n,a in literal_calls(sources,tools)]
                self.assertIn(sequence,gold)

    def test_duplicate_states_and_conflicting_edges_are_not_silently_accepted(self):
        r=deepcopy(self.record);r['nodes'].append(deepcopy(r['nodes'][0]))
        with self.assertRaises(ValueError):compile_dfa(r)
        r=deepcopy(self.record);r['nodes'][0]['transitions'].append({'symbols':['A'],'from':'G0','to':'G2'})
        with self.assertRaises(ValueError):compile_dfa(r)

    def test_missing_prompt_is_not_silently_joined_and_unknown_policy_fails(self):
        artifact = trace(self.record, ['A','C'])
        del artifact['prompt']
        self.assertEqual(evaluate_paper(artifact,[self.record])['status'],'unscored')
        with self.assertRaises(ValueError):evaluate_artifact(artifact,policy='unknown')

    def test_rescore_deduplicates_windows_paths_and_preserves_source(self):
        from are_integration.rescore import rescore_batch
        from function_calling.computations_smoke import ComputationsScript
        from function_calling.core_computations import run_computations
        artifact = run_computations(ComputationsScript())
        with TemporaryDirectory() as directory:
            run_path = Path(directory)/'run.json'
            run_path.write_text(json.dumps(artifact))
            before = run_path.read_bytes()
            entry = {'artifact':str(run_path).replace('/', '\\'), 'prompt_id':'computations_1'}
            source = Path(directory)/'summary.json'
            source.write_text(json.dumps({'reused_runs':[entry], 'runs':[entry,
                {'prompt_id':'web_browsing_1','blocked_reason':'missing fixture'}]}))
            result = rescore_batch(source)
            self.assertEqual(result['counts'], {'scored':1, 'blocked':1})
            self.assertEqual(result['means']['path_correctness'],1)
            self.assertEqual(result['defined_counts']['efficiency'],1)
            self.assertEqual(run_path.read_bytes(),before)

if __name__=='__main__':unittest.main()
