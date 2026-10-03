"""Deterministic layered layout and obstacle-aware orthogonal connections."""

from collections import Counter, defaultdict, deque
import heapq
import textwrap


def packet_symbol(edge):
    """Identify a real animated transfer for both rendering and clearance."""
    if not edge.get("animate"):
        return None
    return {"message": "message", "deploy": "package"}.get(edge.get("transport"))


class RouteError(ValueError):
    def __init__(self, edge, message):
        self.edge = edge
        super().__init__(message)


def layered_ranks(nodes, edges):
    """Longest-path ranks in a spanning DAG; feedback edges remain drawable."""
    adjacency = {node["id"]: [] for node in nodes}
    incoming = Counter()
    for edge in edges:
        source, target = edge["from"], edge["to"]
        stack, seen = [target], set()
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(adjacency[current])
        if source not in seen:
            adjacency[source].append(target)
            incoming[target] += 1
    ranks = {node["id"]: 0 for node in nodes}
    pending = deque(node_id for node_id in adjacency if not incoming[node_id])
    while pending:
        source = pending.popleft()
        for target in adjacency[source]:
            ranks[target] = max(ranks[target], ranks[source] + 1)
            incoming[target] -= 1
            if not incoming[target]:
                pending.append(target)
    return ranks


def graph_layout(nodes, edges, groups=None, vertical=False):
    ranks = layered_ranks(nodes, edges)
    display_ranks = dict(ranks)
    ownership = {node["id"]: node.get("group") for node in nodes}
    connections = {(edge["from"], edge["to"]) for edge in edges}
    bidirectional = any(source != target and (target, source) in connections and ownership[source] and ownership[source] == ownership[target] for source, target in connections)
    column_step = 432 if bidirectional else 368
    if groups and not vertical:
        # An external sink of an ownership hub belongs below that hub, not in
        # the thread/child column. This gives persistence its own vertical lane.
        by_id = {node["id"]: node for node in nodes}
        for node in nodes:
            parents = [by_id[edge["from"]] for edge in edges if edge["to"] == node["id"]]
            if "group" not in node and len(parents) == 1 and "group" in parents[0]:
                parent = parents[0]
                siblings = [by_id[edge["to"]] for edge in edges if edge["from"] == parent["id"] and edge["to"] != node["id"]]
                if len(siblings) > 1 and all(sibling.get("group") == parent["group"] for sibling in siblings):
                    display_ranks[node["id"]] = ranks[parent["id"]]
    bands = [(group["id"], [node for node in nodes if node.get("group") == group["id"]]) for group in groups or []]
    ungrouped = [node for node in nodes if "group" not in node]
    if vertical:
        # Ownership blocks remain contiguous, but external triggers must not be
        # pushed beneath the runtime they invoke merely because it is grouped.
        blocks = bands + [("", [node]) for node in ungrouped]
        blocks.sort(key=lambda block: (min(ranks[node["id"]] for node in block[1]), min(nodes.index(node) for node in block[1])))
        bands = []
        for band, members in blocks:
            if bands and not band and not bands[-1][0]:
                bands[-1][1].extend(members)
            else:
                bands.append((band, members))
    elif ungrouped:
        bands.append(("", ungrouped))
    positions, offset_y = {}, 54
    for band, members in bands:
        if vertical:
            members.sort(key=lambda node: ranks[node["id"]])
        column_y = Counter()
        for node in members:
            lines = textwrap.wrap(node["label"], width=15, break_long_words=True) or [node["label"]]
            metadata = textwrap.wrap(node.get("meta", ""), width=18)
            height = max(114, 96 + max(0, len(lines)-1)*22 + len(metadata)*18)
            rank = 0 if vertical else display_ranks[node["id"]]
            positions[node["id"]] = (92 + rank*column_step, offset_y + (52 if band else 0) + column_y[rank], 246, height, lines)
            column_y[rank] += height + 80
        if band and not vertical:
            tallest = max(column_y.values(), default=0)
            for node in members:
                x, y, w, h, lines = positions[node["id"]]
                positions[node["id"]] = (x, y+(tallest-column_y[display_ranks[node["id"]]])/2, w, h, lines)
        offset_y += max(column_y.values(), default=0) + (70 if band else 28)
    width = 430 if vertical else 430 + max(display_ranks.values(), default=0)*column_step
    return positions, width, offset_y + 30


def group_bounds(visual, positions):
    result = []
    for group in visual.get("groups", []):
        members = [positions[node["id"]] for node in visual["nodes"] if node.get("group") == group["id"]]
        x, y = min(item[0] for item in members)-18, min(item[1] for item in members)-44
        width = max(item[0]+item[2] for item in members)-x+18
        height = max(item[1]+item[3] for item in members)-y+18
        result.append((group, (x, y, width, height), (x, y, width, 34)))
    return result


def overlaps(a, b):
    x, y, w, h = a
    bx, by, bw, bh = b
    return x < bx+bw and x+w > bx and y < by+bh and y+h > by


def segment_hits(a, b, rectangle):
    x, y, w, h = rectangle
    if a[0] == b[0]:
        return x < a[0] < x+w and max(a[1], b[1]) > y and min(a[1], b[1]) < y+h
    return y < a[1] < y+h and max(a[0], b[0]) > x and min(a[0], b[0]) < x+w


def simplify(points):
    result = []
    for point in points:
        if result and point == result[-1]:
            continue
        if len(result) > 1 and (result[-2][0] == result[-1][0] == point[0] or result[-2][1] == result[-1][1] == point[1]):
            result[-1] = point
        else:
            result.append(point)
    return result


def port_requests(visual, positions, vertical):
    requests, directions = defaultdict(list), {}
    by_id = {node["id"]: node for node in visual["nodes"]}
    for index, edge in enumerate(visual["edges"]):
        sx, sy, sw, sh, _ = positions[edge["from"]]
        tx, ty, tw, th, _ = positions[edge["to"]]
        if edge["from"] == edge["to"]:
            source, target = "right", "bottom"
        elif vertical or tx == sx:
            clear_downward = ty > sy and not any(
                node_id not in (edge["from"], edge["to"]) and ox < sx+sw/2 < ox+ow and oy < ty and oy+oh > sy+sh
                for node_id, (ox, oy, ow, oh, _) in positions.items()
            )
            if by_id[edge["to"]].get("group") and by_id[edge["from"]].get("group") != by_id[edge["to"]].get("group"):
                clear_downward = False
            if clear_downward:
                source, target = "bottom", "top"
            else:
                source = target = "right" if ty > sy else "left"
        elif tx > sx:
            source, target = "right", "left"
        elif by_id[edge["from"]].get("group") and by_id[edge["from"]].get("group") == by_id[edge["to"]].get("group"):
            source, target = "left", "right"
        else:
            source, target = "bottom", "bottom"
        directions[index] = (source, target)
        for node_id, side, role, other in ((edge["from"], source, "start", (tx+tw/2, ty+th/2)), (edge["to"], target, "end", (sx+sw/2, sy+sh/2))):
            order = other[1] if side in ("left", "right") else other[0]
            # At equal height, nearby upstream nodes get the upper ports;
            # long bypass connections enter below them instead of crossing.
            distance_order = -other[0] if side == "left" else other[0] if side == "right" else other[1]
            requests[node_id, side].append((order, distance_order, index, role))
    ports = {}
    vectors = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}
    for (node_id, side), items in requests.items():
        x, y, width, height, _ = positions[node_id]
        for slot, (_, _, index, role) in enumerate(sorted(items), 1):
            fraction = slot/(len(items)+1)
            if side in ("left", "right"):
                anchor = (x if side == "left" else x+width, round(y+20+(height-40)*fraction, 2))
            else:
                anchor = (round(x+24+(width-48)*fraction, 2), y if side == "top" else y+height)
            vector = vectors[side]
            distance = 4 if role == "start" else 9
            tip = (anchor[0]+vector[0]*distance, anchor[1]+vector[1]*distance)
            stem = (anchor[0]+vector[0]*32, anchor[1]+vector[1]*32)
            ports[index, role] = (tip, stem, vector)
    for index, edge in enumerate(visual["edges"]):
        source_side, target_side = directions[index]
        if source_side not in ("left", "right") or target_side not in ("left", "right"):
            continue
        source_count = len(requests[edge["from"], source_side])
        target_count = len(requests[edge["to"], target_side])
        if source_count == 1:
            role, node_id, desired = "start", edge["from"], ports[index, "end"][0][1]
        elif target_count == 1:
            role, node_id, desired = "end", edge["to"], ports[index, "start"][0][1]
        else:
            continue
        _, y, _, height, _ = positions[node_id]
        if y+20 <= desired <= y+height-20:
            tip, stem, vector = ports[index, role]
            ports[index, role] = ((tip[0], desired), (stem[0], desired), vector)
    return ports


def orthogonal_route(start, end, initial, final, xs, ys, obstacles, used):
    if start == end:
        return [start]
    start_grid, end_grid = (xs.index(start[0]), ys.index(start[1])), (xs.index(end[0]), ys.index(end[1]))
    state = (*start_grid, *initial)
    pending = [(0, 0, state)]
    costs, previous = {state: 0}, {}
    serial = 0
    lane = None
    if initial == final and initial[0] and end[1] != start[1]:
        lane = start[0] if (end[1]-start[1])*initial[0] < 0 else end[0]
    while pending:
        _, _, current = heapq.heappop(pending)
        ix, iy, dx, dy = current
        # The explicit final stem already supplies a clear arrowhead approach.
        # Requiring its direction one step earlier creates artificial U-turns.
        if (ix, iy) == end_grid and (dx, dy) != (-final[0], -final[1]):
            path = []
            while current in previous:
                path.append((xs[current[0]], ys[current[1]]))
                current = previous[current]
            return simplify([(xs[current[0]], ys[current[1]])] + list(reversed(path)))
        point = (xs[ix], ys[iy])
        for vx, vy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (vx, vy) == (-dx, -dy):
                continue
            nx, ny = ix+vx, iy+vy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            target = (xs[nx], ys[ny])
            if any(segment_hits(point, target, obstacle) for obstacle in obstacles):
                continue
            penalty, blocked = 0, False
            for a, b in used:
                if vx and a[1] == b[1] == point[1] and min(max(a[0], b[0]), max(point[0], target[0])) > max(min(a[0], b[0]), min(point[0], target[0])):
                    blocked = True
                    break
                elif vy and a[0] == b[0] == point[0] and min(max(a[1], b[1]), max(point[1], target[1])) > max(min(a[1], b[1]), min(point[1], target[1])):
                    blocked = True
                    break
                elif vx and a[0] == b[0] and min(point[0], target[0]) < a[0] < max(point[0], target[0]) and min(a[1], b[1]) < point[1] < max(a[1], b[1]):
                    penalty += 100
                elif vy and a[1] == b[1] and min(point[1], target[1]) < a[1] < max(point[1], target[1]) and min(a[0], b[0]) < point[0] < max(a[0], b[0]):
                    penalty += 100
                elif vx and a[1] == b[1] and abs(a[1]-point[1]) < 28 and min(max(a[0], b[0]), max(point[0], target[0])) > max(min(a[0], b[0]), min(point[0], target[0])):
                    penalty += 20
                elif vy and a[0] == b[0] and abs(a[0]-point[0]) < 28 and min(max(a[1], b[1]), max(point[1], target[1])) > max(min(a[1], b[1]), min(point[1], target[1])):
                    penalty += 20
            if blocked:
                continue
            length = abs(target[0]-point[0]) + abs(target[1]-point[1])
            lane_penalty = length*abs(point[0]-lane)/1000 if vy and lane is not None else 0
            terminal_bend = 20 if (nx, ny) == end_grid and (vx, vy) != final else 0
            cost = costs[ix, iy, dx, dy] + length + (20 if (vx, vy) != (dx, dy) else 0) + terminal_bend + penalty + lane_penalty
            next_state = (nx, ny, vx, vy)
            if cost < costs.get(next_state, float("inf")):
                costs[next_state], previous[next_state] = cost, (ix, iy, dx, dy)
                serial += 1
                estimate = abs(target[0]-end[0]) + abs(target[1]-end[1])
                heapq.heappush(pending, (cost+estimate, serial, next_state))
    return None


def route_graph(visual, vertical=False):
    positions, width, height = graph_layout(visual["nodes"], visual["edges"], visual.get("groups"), vertical)
    groups = group_bounds(visual, positions)
    obstacles = [(x-18, y-18, w+36, h+36) for x, y, w, h, _ in positions.values()]
    sequence_edges = {step["edge"]-1 for step in visual.get("sequence", []) if "edge" in step}
    moving_edges = sequence_edges | {index for index, edge in enumerate(visual["edges"]) if packet_symbol(edge)}
    heading_clearance = 16 if moving_edges else 8
    obstacles += [(x-heading_clearance, y-heading_clearance, w+heading_clearance*2, h+heading_clearance*2) for _, _, (x, y, w, h) in groups]
    ports = port_requests(visual, positions, vertical)
    xs, ys = {22, 44, 60, width-60, width-44, width-22}, {22, 32, height-32, height-22}
    for x, y, w, h in obstacles:
        xs.update((x, x+w))
        ys.update((y, y+h, y-14, y+h+14))
    for _, stem, _ in ports.values():
        xs.add(stem[0])
        ys.add(stem[1])
    xs = sorted(x for x in xs if 0 < x < width)
    ys = sorted(y for y in ys if 0 < y < height)
    routes, used = [], []
    for index, edge in enumerate(visual["edges"]):
        source_tip, source_stem, source_vector = ports[index, "start"]
        target_tip, target_stem, target_vector = ports[index, "end"]
        path = orthogonal_route(source_stem, target_stem, source_vector, (-target_vector[0], -target_vector[1]), xs, ys, obstacles, used)
        if path is None:
            raise RouteError(index, "No clear connector corridor is available.")
        path = simplify([source_tip] + path + [target_tip])
        routes.append({"points": path, "source": edge["from"], "target": edge["to"]})
        used.extend(zip(path, path[1:]))
    occupied = [(x-5, y-5, w+10, h+10) for x, y, w, h, _ in positions.values()]
    occupied += [header for _, _, header in groups]
    # Protect arrowheads and all other paths when placing a numbered connection.
    occupied += [(route["points"][-1][0]-18, route["points"][-1][1]-18, 36, 36) for route in routes]
    for index, route in enumerate(routes):
        candidates = []
        packet = index in moving_edges
        for a, b in zip(route["points"], route["points"][1:]):
            length = abs(b[0]-a[0])+abs(b[1]-a[1])
            for fraction in (.5, .3, .7, .2, .8):
                x, y = a[0]+(b[0]-a[0])*fraction, a[1]+(b[1]-a[1])*fraction
                if packet:
                    offsets = ((0, -32), (0, 32)) if a[1] == b[1] else ((-36, 0), (36, 0))
                    candidates.extend((length, x+dx, y+dy) for dx, dy in offsets)
                else:
                    candidates.append((length, x, y))
        for _, x, y in sorted(candidates, key=lambda item: -item[0]):
            box = (x-17, y-12, 34, 24)
            if x < 18 or x > width-18 or y < 13 or y > height-13 or any(overlaps(box, obstacle) for obstacle in occupied):
                continue
            blocked = False
            for other_index, other in enumerate(routes):
                other_packet = other_index in moving_edges
                if other_index == index and not packet:
                    continue
                margin = 14 if other_packet else 4
                if any(segment_hits(a, b, (x-17-margin, y-12-margin, 34+margin*2, 24+margin*2)) for a, b in zip(other["points"], other["points"][1:])):
                    blocked = True
                    break
            if blocked:
                continue
            route["label"] = (x, y)
            occupied.append((x-21, y-16, 42, 32))
            break
        else:
            raise RouteError(index, "The connection number cannot be placed without obscuring a node, arrowhead, or another connection.")
    return {"positions": positions, "width": width, "height": height, "groups": groups, "routes": routes}


def path_data(points):
    # Small rounded bends retain distinct straight terminal segments.
    first = points[0]
    pieces = [f"M {first[0]:g} {first[1]:g}"]
    for index, corner in enumerate(points[1:-1], 1):
        before, after = points[index-1], points[index+1]
        distance_a = abs(corner[0]-before[0])+abs(corner[1]-before[1])
        distance_b = abs(after[0]-corner[0])+abs(after[1]-corner[1])
        radius = min(6, distance_a/2, distance_b/2)
        enter = (corner[0]+(before[0]-corner[0])*radius/distance_a, corner[1]+(before[1]-corner[1])*radius/distance_a)
        leave = (corner[0]+(after[0]-corner[0])*radius/distance_b, corner[1]+(after[1]-corner[1])*radius/distance_b)
        pieces.append(f"L {enter[0]:g} {enter[1]:g} Q {corner[0]:g} {corner[1]:g} {leave[0]:g} {leave[1]:g}")
    pieces.append(f"L {points[-1][0]:g} {points[-1][1]:g}")
    return " ".join(pieces)
