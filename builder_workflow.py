"""Validation for Builder workflow/tree definitions."""

import re


NODE_TYPES = {
    'choice',
    'field',
    'calculation',
    'summary',
    'save',
    'destination',
}

CALCULATIONS = {
    'finance_calculate',
}


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(
        r'[a-zA-Z][a-zA-Z0-9_-]{0,79}', value
    ):
        raise ValueError('Invalid workflow identifier.')
    return value


def short_text(value, limit=120):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Invalid workflow text.')
    return value.strip()


def validate(workflow, fields):
    """Validate and return a clean workflow definition."""
    if workflow in (None, {}):
        return None

    if not isinstance(workflow, dict):
        raise ValueError('Invalid workflow.')

    if workflow.get('version', 1) != 1:
        raise ValueError('Unsupported workflow version.')

    field_ids = {field['id'] for field in fields}

    nodes = workflow.get('nodes')
    edges = workflow.get('edges')

    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 100:
        raise ValueError('Use between 1 and 100 workflow nodes.')

    if not isinstance(edges, list) or len(edges) > 250:
        raise ValueError('Use up to 250 workflow connections.')

    clean_nodes = []
    node_ids = set()

    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError('Invalid workflow node.')

        node_id = identity(node.get('id'))

        if node_id in node_ids:
            raise ValueError('Workflow node identifiers must be unique.')

        node_ids.add(node_id)

        node_type = node.get('type')

        if node_type not in NODE_TYPES:
            raise ValueError('Unsupported workflow node type.')

        clean = {
            'id': node_id,
            'type': node_type,
        }

        if node_type in ('choice', 'field'):
            field_id = identity(node.get('field_id'))

            if field_id not in field_ids:
                raise ValueError(
                    f'Workflow field {field_id} does not exist in this layout.'
                )

            clean['field_id'] = field_id

        elif node_type == 'calculation':
            operation = short_text(node.get('operation'))

            if operation not in CALCULATIONS:
                raise ValueError('Unsupported workflow calculation.')

            inputs = node.get('inputs', [])
            outputs = node.get('outputs', [])

            if (
                not isinstance(inputs, list)
                or any(item not in field_ids for item in inputs)
            ):
                raise ValueError('Workflow calculation contains an invalid input.')

            if (
                not isinstance(outputs, list)
                or any(
                    not isinstance(item, str)
                    or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,79}', item)
                    for item in outputs
                )
            ):
                raise ValueError('Workflow calculation contains an invalid output.')

            clean['operation'] = operation
            clean['inputs'] = inputs
            clean['outputs'] = outputs

        elif node_type == 'summary':
            clean['title'] = short_text(
                node.get('title', 'Summary / Confirm')
            )
            clean['visible_fields'] = short_text(
                node.get('visible_fields', 'current_branch')
            )

        elif node_type == 'save':
            clean['record_type'] = short_text(
                node.get('record_type', 'record')
            )

        elif node_type == 'destination':
            clean['screen'] = short_text(node.get('screen'))

        clean_nodes.append(clean)

    start_node = identity(workflow.get('start_node'))

    if start_node not in node_ids:
        raise ValueError('Workflow start node does not exist.')

    clean_edges = []

    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError('Invalid workflow connection.')

        source = identity(edge.get('from'))
        destination = identity(edge.get('to'))

        if source not in node_ids or destination not in node_ids:
            raise ValueError(
                'Workflow connections must point to existing nodes.'
            )

        clean = {
            'from': source,
            'to': destination,
        }

        condition = edge.get('when')

        if condition is not None:
            if not isinstance(condition, dict):
                raise ValueError('Invalid workflow condition.')

            field_id = identity(condition.get('field'))

            if field_id not in field_ids:
                raise ValueError(
                    'Workflow condition refers to an unknown field.'
                )

            if 'equals' not in condition:
                raise ValueError(
                    'Workflow condition requires an equals value.'
                )

            equals = condition['equals']

            if equals is not None and not isinstance(
                equals, (str, bool, int, float)
            ):
                raise ValueError('Invalid workflow comparison value.')

            clean['when'] = {
                'field': field_id,
                'equals': equals,
            }

        if edge.get('action'):
            clean['action'] = short_text(edge['action'], 40)

        if edge.get('on'):
            clean['on'] = short_text(edge['on'], 40)

        clean_edges.append(clean)

    # Make sure every node is connected to the tree.
    reachable = {start_node}
    changed = True

    while changed:
        changed = False

        for edge in clean_edges:
            if edge['from'] in reachable and edge['to'] not in reachable:
                reachable.add(edge['to'])
                changed = True

    missing = node_ids - reachable

    if missing:
        raise ValueError(
            'Workflow contains disconnected nodes: '
            + ', '.join(sorted(missing))
        )

    return {
        'version': 1,
        'start_node': start_node,
        'nodes': clean_nodes,
        'edges': clean_edges,
    }