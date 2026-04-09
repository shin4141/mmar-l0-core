# MMAR Debate Public Fixed Demo Notes

最終更新: 2026-03-26

## Canonical

- 公開固定デモの canonical port は `8912`
- 確認対象 URL は `http://127.0.0.1:8912/mmar/apps/debate/debate.html`

## 実行契約

- `Run Fixed Debate` は fixture を読む
- public fixed demo では `/api/debate` を呼ばない
- 実行成功時の output meta は `3 turns · fixed demo · fixture`

## 誤読注意

- `turn_count=6` は `#turn-log .turn-copy` の数を見ている
- これは `Turn 1 A / Turn 1 B / Turn 2 A / Turn 2 B / Turn 3 A / Turn 3 B` の 6 speaker blocks
- したがって `3 turns` と矛盾しない

## 壊れた時に最初に見るログ

順番:

1. `run_click_received`
2. `public_fixed_demo_branch_entered`
3. `fixture_loader_entered`
4. `fixture_fetch_succeeded`

この並びが出ていれば、

- click は受けている
- public fixed branch に入っている
- fixture loader まで到達している
- fixture fetch は成功している

## 復旧基点 snapshots

- recovery:
  - [snapshot_20260325_231332_public_fixed_demo_recovery](/Users/sn/workspaces/mmar-l0-core/snapshots/snapshot_20260325_231332_public_fixed_demo_recovery)
- meta_alignment:
  - [snapshot_20260326_000029_public_fixed_demo_meta_alignment](/Users/sn/workspaces/mmar-l0-core/snapshots/snapshot_20260326_000029_public_fixed_demo_meta_alignment)
- run_recovery:
  - [snapshot_20260326_001641_public_fixed_demo_run_recovery](/Users/sn/workspaces/mmar-l0-core/snapshots/snapshot_20260326_001641_public_fixed_demo_run_recovery)
- contract_lock:
  - [snapshot_20260326_004256_public_fixed_demo_contract_lock](/Users/sn/workspaces/mmar-l0-core/snapshots/snapshot_20260326_004256_public_fixed_demo_contract_lock)

## 次回の最短確認

1. `8912` の header で `public-fixed` を確認
2. `Run Fixed Debate` を押す
3. output meta が `3 turns · fixed demo · fixture` になるか確認
4. Turn Log が 3 turns 分出るか確認
5. capture summary では `api_debate_called=false` を確認
