import json


with open('repo_maps/requests/requests_ctags_map.json', 'r') as f:
    content = f.read()

chars = len(content)
estimated_tokens = chars // 4

print ('Unfiltered')
print(f'Characters: {chars:,}')
print(f'Estimated tokens: {estimated_tokens:,}')


with open('repo_maps/requests/requests_ctags_map_filtered.json', 'r') as f:
    content = f.read()

chars = len(content)
estimated_tokens = chars // 4

print ('Filtered')
print(f'Characters: {chars:,}')
print(f'Estimated tokens: {estimated_tokens:,}')

with open('repo_maps/requests/requests_ctags_map_filtered.json', 'r') as f:
    ctags = [json.loads(l) for l in f if l.strip()]

with open('repo_maps/requests/requests_ast_map.json', 'r') as f:
    ast_map = [json.loads(l) for l in f if l.strip()]

print(f'ctags records: {len(ctags)}')
print(f'AST records: {len(ast_map)}')

# what kinds does ctags have?
from collections import Counter
print(Counter(t['kind'] for t in ctags))

# what types does AST have?
print(Counter(t['type'] for t in ast_map))