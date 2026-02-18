#!/usr/bin/env python3
import json

with open('workflow.ipynb', 'r') as f:
    nb = json.load(f)

# Get the main code cell
for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        if 'generate_scenarios' in source:
            try:
                compile(source, 'workflow', 'exec')
                print('✓ Code compiles successfully!')
                
                # Check the specific area around line 689
                lines = source.split('\n')
                print(f'\nTotal lines: {len(lines)}')
                print('\nLines 698-705:')
                for i in range(698, min(706, len(lines))):
                    spaces = len(lines[i]) - len(lines[i].lstrip())
                    print(f'{i} [{spaces:2d}sp]: {lines[i][:80]}')
                    
            except SyntaxError as e:
                print(f'✗ Syntax error at line {e.lineno}: {e.msg}')
                if e.lineno:
                    lines = source.split('\n')
                    print(f'Line {e.lineno}: {lines[e.lineno-1][:100]}')
                    print('\nContext:')
                    for i in range(max(0, e.lineno-5), min(len(lines), e.lineno+5)):
                        spaces = len(lines[i]) - len(lines[i].lstrip())
                        print(f'{i} [{spaces:2d}sp]: {lines[i][:80]}')
            break
