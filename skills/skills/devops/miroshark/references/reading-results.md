# Reading MiroShark Simulation Results

After a simulation completes (or crashes mid-run), results live in:
`/root/MiroShark/backend/uploads/simulations/<simulation_id>/`

## Key files

| File | Content |
|---|---|
| `trajectory.json` | Twitter/Reddit snapshots per round — posts, actions, belief drift |
| `trajectory_polymarket.json` | Prediction market snapshots — market prices, agent positions |
| `belief_states_twitter.json` | Final belief positions per agent (Twitter) |
| `belief_states_reddit.json` | Final belief positions per agent (Reddit) |
| `belief_states_polymarket.json` | Final belief positions per agent (Polymarket) |
| `run_state.json` | Process state — current_round, error, timing |
| `simulation.log` | Round-by-round progress log |
| `*_profiles.json` / `*.csv` | Agent profiles (generated during prepare) |

## trajectory.json structure
```json
{
  "topics": ["topic1", "topic2"],
  "total_rounds": 72,
  "snapshots": [{"round": 0, "actions": [...], "posts": [...]}, ...],
  "belief_trajectories": {
    "topic_name": [{"round": 0, "mean": 0.65, "min": 0.5, "max": 0.8, "spread": 0.3, "count": 2}, ...]
  },
  "opinion_convergence": {
    "topic_name": 0.15  // positive = convergence, negative = divergence
  }
}
```

## Extracting partial results (after crash)
```python
import json
d = json.load(open('trajectory.json'))
print(f'Rounds completed: {len(d["snapshots"])}')
print(f'Last round beliefs:')
for topic, traj in d['belief_trajectories'].items():
    last = traj[-1]
    print(f'  {topic}: {last["mean"]:.1%} (spread {last["spread"]:.1%})')
print(f'Opinion convergence:')
for topic, conv in d['opinion_convergence'].items():
    direction = "consensus" if conv > 0.1 else "divergence" if conv < -0.1 else "stable"
    print(f'  {topic}: {conv:+.1%} ({direction})')
```

## Polymarket data
```python
d = json.load(open('trajectory_polymarket.json'))
for snap in d['snapshots'][-3:]:
    for agent_id, positions in snap.get('belief_positions', {}).items():
        for topic, price in positions.items():
            print(f'Round {snap["round_num"]}: {topic} = {price:.1%}')
```

## Interpreting results
- **belief_trajectories**: Track how agent beliefs evolve round-over-round. `mean` is average across agents, `spread` is max-min disagreement.
- **opinion_convergence**: Positive = agents converging toward agreement. Negative = agents diverging (polarization).
- **Polymarket prices**: Interpret as probability. 80% = agents think 80% chance of event happening.
- **spread**: High spread (>0.2) = significant disagreement between agents. Low spread (<0.05) = consensus.
