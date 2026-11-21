-- 2026-11-21 (owner): « les domaines spécialisés doivent avoir un vrai intérêt par rapport aux modèles généraux,
-- donc on [reste] avec les index de AA et de Design Arena ». The design / web specialists are ranked on their Design
-- Arena board alone (LMArena webdev, BridgeBench and AA 3D no longer weigh nor raise proposals; scores still
-- collected). Tasks with an AA index: 044. Tasks with neither (coding, document, long_context, science, vision,
-- voice_assist, writing): unchanged until the owner decides.
begin;
delete from models.task_benchmarks where (task, bench_task) not in
    (('3d', '3d'), ('dataviz', 'dataviz'), ('frontend', 'website'), ('fullstack', 'fullstack'), ('gamedev', 'gamedev'),
     ('mobile_app', 'mobileapps'), ('svg', 'svg'), ('ui_component', 'uicomponent'))
  and task in ('3d', 'dataviz', 'frontend', 'fullstack', 'gamedev', 'mobile_app', 'svg', 'ui_component');
update models.task_benchmarks set is_primary = true, weight = 1.0
  where task in ('3d', 'dataviz', 'frontend', 'fullstack', 'gamedev', 'mobile_app', 'svg', 'ui_component');
insert into models.schema_migrations (version) values ('045_design_tasks_on_design_arena') on conflict do nothing;
commit;
