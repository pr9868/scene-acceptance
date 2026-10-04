"""Explain scene, requirement provenance and coverage without changing verdicts."""
from collections import Counter
from html import escape
import json
from .coverage import domain_for
from .model import digest_json

AREAS = {'geometry':'Geometry and structure', 'materials':'Materials and bindings',
         'textures':'Texture files and content', 'uv':'UV mapping', 'motion':'Motion',
         'physics':'Physics setup', 'simulation':'Simulated behavior',
         'appearance':'Rendered appearance', 'delivery':'Delivery and dependencies', 'other':'Other / unclassified'}
GROUPS = {
    'general': ('General structural and delivery checks', 'Rules that do not need a task-specific target. They can still be selected by a person.'),
    'human': ('Checks linked to human specifications', 'A human source is explicitly recorded; this is reported provenance, not authenticated authorship.'),
    'configured': ('Checks linked to application, agent or preset specifications', 'Targets come from another recorded source; they are not labeled human instructions.'),
    'unrecorded': ('Target-based checks; source unrecorded', 'Configured targets exist, but the record does not say who supplied them.'),
    'unclassified': ('Other checks; basis unclassified', 'The provider or legacy record does not establish whether a task target is required.'),
}
STATUSES = ('pass', 'warning', 'fail', 'unknown', 'error', 'not_applicable')
STATUS_LABELS = {'PASS':'Pass', 'PASS_WITH_WARNINGS':'Warning', 'FAIL':'Fail',
                 'UNKNOWN':'Unknown', 'ERROR':'Execution error', 'PARTIAL_COVERAGE':'Partial coverage',
                 'NO_APPLICABLE_SUBJECTS':'No applicable subjects', 'NOT_APPLICABLE':'Not applicable'}
SOURCE_LABELS = {'human':'Human (recorded)', 'application':'Application', 'agent':'Agent',
                 'preset':'Preset', 'unrecorded':'Source unrecorded'}
PRESET_TARGETS = {
    'common.metadata':'Use metre units, Z-up and a default prim',
    'common.geometry':'Use supported geometry with valid mesh indices and finite values',
    'tray.dimensions':'Tray outer size: 300 × 200 × 80 mm',
    'tray.cavity':'Tray opening: 280 × 180 mm; 10 mm floor and prescribed open rim',
    'tray.closure':'Tray material boundary is closed and has the prescribed volume',
    'tray.transform':'Tray stays at baseline or moves +400 mm along world X, as selected',
    'tray.fixture':'Protected fixture keeps its prescribed dimensions and position',
    'tray.preserved':'Preserve all unrelated tray/baseline authored fields',
    'panel.dimensions':'Panel size: 240 × 160 mm in XY at Z=0; X/Y offset is free',
    'panel.shader':'Named texture feeds the panel diffuse color through the prescribed UV graph',
    'panel.uv':'UV coordinates cover the whole panel with the prescribed affine mapping',
    'panel.pixels':'256 × 256 RGB image with red, green, blue and white quadrants',
    'panel.equivalence':'PNG and JPEG scene authoring match apart from the image reference',
    'motion.clock':'Saved animation: time codes 12–156 at 48 per second',
    'motion.lengths':'Crank radius 42 mm, rod 140 mm and prescribed centre/slider line at sample times',
    'motion.cycle':'Start at 25°, follow one counterclockwise cycle and close the loop',
    'motion.trajectory':'Compare with a constant-speed crank-slider reference (advisory in the example)',
    'motion.connections':'Both attachments remain within 0.5 mm at 514 diagnostic times',
    'motion.geometry':'Crank, rod and slider contain authored geometry',
    'physics.parameters':'Block mass is 1.25 kg; friction matches the selected variant',
    'physics.preserved':'Preserve the supplied physics base except the three allowed parameters',
}


def check_label(check):
    if check['pack']=='brief.measurements':
        return {'bounds':'Named geometry matches specified size and centre','children':'Named group has the specified number of parts',
                'axis_gap':'Specified gap between named objects','image_pixels':'Delivered texture matches the supplied reference image',
                'metadata':'Authored stage settings match the brief'}.get(check['check'],check['check'])
    if check['pack']=='brief.four-job': return PRESET_TARGETS.get(check['check'],check['check'])
    return {('scene.audit','files'):'Referenced local files are present',
            ('scene.audit','textures'):'Referenced images can be decoded',
            ('scene.audit','authored_motion'):'Saved transform animation has usable timing and finite values',
            ('textures.decode','image'):'Selected texture can be decoded',
            ('motion.connection','distance'):'Named attachment points stay within the specified gap',
            ('motion.timing','clock'):'Saved clock matches the requested duration and rate',
            ('physics.incline-worker','displacement'):'Simulated displacement stays within the requested limit',
            ('materials','delivery'):'Named objects have the specified material bindings',
            ('geometry','contract'):'Geometry and edits satisfy the supplied contract'}.get((check['pack'],check['check']),
              ', '.join(check.get('parameters',{}).get('validators',check.get('parameters',{}).get('rules',[]))) or check['pack']+'.'+check['check'])
E = lambda value: escape(str(value), quote=True)


def area_for(check):
    p, name = check.get('pack'), check.get('check')
    if p == 'brief.measurements':
        if name=='metadata' and any(k in check.get('parameters',{}).get('values',{}) for k in ('startTimeCode','endTimeCode','timeCodesPerSecond')):return 'motion'
        return 'textures' if name=='image_pixels' else 'geometry'
    if p == 'scene.audit': return {'files':'delivery','textures':'textures','authored_motion':'motion'}.get(name,'other')
    if p == 'brief.four-job':
        if name.startswith('common.'): return 'geometry'
        if name == 'panel.pixels': return 'textures'
        if name == 'panel.uv': return 'uv'
        if name in ('panel.shader','panel.equivalence'): return 'materials'
        return {'tray':'geometry','panel':'geometry','motion':'motion','physics':'physics'}.get(name.split('.')[0],'other')
    if p == 'nvidia.asset-validator':
        rules=check.get('parameters',{}).get('rules',[])
        if any(x in ('MassChecker','RigidBodyChecker','ColliderChecker','PhysicsJointChecker') for x in rules): return 'physics'
    if p not in ('openusd','nvidia.asset-validator','geometry','materials','motion','motion.timing','motion.connection','textures.decode','physics.incline-worker'):
        return 'other'
    return {'structure_geometry':'geometry','material_delivery':'materials','texture_readability':'textures',
            'texture_content':'textures','uv_mapping':'uv','authored_motion':'motion','motion_requirements':'motion',
            'physics_structure':'physics','simulation':'simulation'}.get(domain_for(check),'other')


def source_for(check):
    if check.get('specification_source'): return check['specification_source']
    if check.get('pack') == 'brief.four-job':
        return {'provided_by':'preset','reference':'Versioned four-job target values; no human authorship inferred'}
    return {'provided_by':'unrecorded','reference':'No specification source recorded'}


def basis_for(check, mapped_sources):
    origins=[x['provided_by'] for x in mapped_sources]
    if check.get('specification_source'): origins.append(check['specification_source']['provided_by'])
    if 'human' in origins: return 'human'
    if any(x in ('application','agent','preset') for x in origins): return 'configured'
    if mapped_sources or check.get('specification_source'): return 'unrecorded'
    if check.get('pack') in ('openusd','nvidia.asset-validator','scene.audit','textures.decode'): return 'general'
    if check.get('pack') == 'brief.four-job': return 'configured'
    if check.get('pack') in ('geometry','materials','motion','motion.timing','motion.connection','physics.incline-worker'): return 'unrecorded'
    return 'unclassified'


def outcome_bucket(status):
    return {'PASS':'pass','PASS_WITH_WARNINGS':'warning','FAIL':'fail','UNKNOWN':'unknown',
            'PARTIAL_COVERAGE':'unknown','ERROR':'error','NO_APPLICABLE_SUBJECTS':'not_applicable',
            'NOT_APPLICABLE':'not_applicable'}.get(status,'unknown')


def count(rows):
    c=Counter(outcome_bucket(r['status']) for r in rows)
    return {s:c[s] for s in STATUSES}


def merged_status(rows):
    states=[r['status'] for r in rows]
    for status in ('ERROR','FAIL','UNKNOWN','PARTIAL_COVERAGE','PASS_WITH_WARNINGS'):
        if status in states: return status
    return 'PASS' if states and all(s=='PASS' for s in states) else 'UNKNOWN'


def build_overview(core, review=None):
    """Derived presentation data. A passed check never proves completeness of a brief."""
    core=core or {}; identity=core.get('identity',{}); coverage=core.get('coverage',{})
    plan={x['id']:x for x in coverage.get('planned',[]) if isinstance(x,dict)}
    audit={x['id']:x for x in coverage.get('audit',{}).get('rows',[])}
    results={x['id']:x for x in core.get('checks',[])}
    if not plan:
        plan={id:dict(id=id,pack='legacy',check=id,required=r.get('required',True),parameters={})
              for id,r in results.items() if not id.startswith('core.')}
    declarations=(review or {}).get('items',[])
    mapping={}; sources={}
    for spec in declarations:
        explicit=spec.get('specification_source')
        inherited=[source_for(plan[i]) for i in spec['check_ids'] if i in plan]
        distinct={s['provided_by'] for s in inherited}
        source=explicit or (inherited[0] if inherited and len(distinct)==1 else
                           {'provided_by':'unrecorded','reference':'Requirement source not recorded; check sources may differ'})
        sources[spec['id']]=source
        for id in spec['check_ids']: mapping.setdefault(id,[]).append(source)
    checks=[]
    for id,p in plan.items():
        r=results.get(id,{}); a=audit.get(id,{})
        observations=r.get('evidence',{}).get('observations',{})
        values={k:observations[k] for k in ('maximum_sampled_gap_m','max_gap_m','maximum_recomputed_displacement_m',
                'whole_max_channel_error','interior_max_channel_error','signed_volume_m3','expected_volume_m3','minimum_m','maximum_m') if isinstance(observations,dict) and k in observations}
        checks.append(dict(id=id,label=check_label(p),pack=p['pack'],check=p['check'],area=area_for(p),
            basis=basis_for(p,mapping.get(id,[])),status=a.get('status',r.get('status','UNKNOWN')),
            required=p.get('required',True),parameters=p.get('parameters',{}),
            source=source_for(p),linked_sources=mapping.get(id,[]),
            method='Simulation worker' if p['pack']=='physics.incline-worker' else 'Provider-defined; not classified' if area_for(p)=='other' else 'Saved artifact inspection',
            subject_unit=a.get('unit','not reported'),subject_counts=a.get('counts'),reason=r.get('reason','No result'),
            observed_values=values,
            evidence_pointer=a.get('evidence_pointer',f'/checks/{list(results).index(id)}' if id in results else None)))
    by_id={x['id']:x for x in checks}
    specs=[]
    for i,entry in enumerate(declarations):
        mapped=[by_id[x] for x in entry['check_ids'] if x in by_id]
        completed=sum(outcome_bucket(x['status']) in ('pass','warning','fail') for x in mapped)
        declared=entry.get('coverage_declaration',{'extent':'unreviewed','reason':'Coverage extent was not declared'})
        if not mapped: extent='No automated coverage'
        elif completed<len(mapped): extent='Automated evidence incomplete'
        elif entry['review_required']: extent='Partial automation; separate review required'
        elif (review or {}).get('mapping_review',{}).get('status')=='pending': extent='Mapped checks ran; mapping review pending'
        elif declared['extent']=='full': extent='Full mapping declared by caller'
        elif declared['extent']=='partial': extent='Partial mapping declared by caller'
        else: extent='Mapped checks ran; coverage extent unreviewed'
        areas=entry.get('areas') or sorted({x['area'] for x in mapped}) or ['delivery' if entry['layer']=='delivery' else 'other']
        specs.append(dict(id=entry['id'],statement=entry['statement'],source=sources[entry['id']],
            areas=areas,required=entry['required'],check_ids=entry['check_ids'],mapped_count=len(mapped),
            completed_count=completed,coverage=extent,coverage_declaration=declared,
            status=('PASS_WITH_WARNINGS' if entry['status']=='PASS' and merged_status(mapped)=='PASS_WITH_WARNINGS' else entry['status']),check_result=merged_status(mapped),review_required=entry['review_required'],
            reason='; '.join(o['reason'] for o in entry['observations'] if o['status']!='PASS') or declared['reason'],
            comparisons=[dict(id=x['id'],parameters=x['parameters'],observed_values=x['observed_values'],status=x['status'],reason=x['reason']) for x in mapped],
            evidence_pointer=f'/items/{i}',declaration_kind='review-plan obligation'))
    # Contracts without a full brief still expose configured targets and their source.
    mapped_ids={id for s in specs for id in s['check_ids']}
    for check in checks:
        if check['id'] in mapped_ids or check['basis'] in ('general','unclassified'): continue
        p=plan[check['id']]
        specs.append(dict(id=check['id'],statement=check['label'],
            source=check['source'],areas=[check['area']],required=check['required'],check_ids=[check['id']],
            mapped_count=1,completed_count=int(outcome_bucket(check['status']) in ('pass','warning','fail')),
            coverage='Target configured; complete specification not mapped',
            coverage_declaration={'extent':'unreviewed','reason':'No requirement-to-evidence map supplied for this target'},
            status=check['status'],check_result=check['status'],review_required=False,
            reason=json.dumps(p['parameters'],sort_keys=True),evidence_pointer=check['evidence_pointer'],
            comparisons=[dict(id=check['id'],parameters=check['parameters'],observed_values=check['observed_values'],status=check['status'],reason=check['reason'])],
            declaration_kind='configured check target'))
    matrix=[]
    for key,(label,note) in GROUPS.items():
        selected=[x for x in checks if x['basis']==key]
        matrix.append(dict(id=key,label=label,note=note,total=len(selected),required=sum(x['required'] for x in selected),
                           advisory=sum(not x['required'] for x in selected),**count(selected)))
    area_rows=[]
    for area,label in AREAS.items():
        selected=[x for x in checks if x['area']==area]; specified=[s for s in specs if area in s['areas']]
        human=[s for s in specified if s['source']['provided_by']=='human']
        area_rows.append(dict(id=area,label=label,checks=len(selected),specifications=len(specified),
            human_specifications=len(human),specification_sources=sorted({s['source']['provided_by'] for s in specified}),
            human_input=f'{len(human)} recorded' if human else 'No human source recorded',
            coverage='; '.join(sorted({s['coverage'] for s in specified})) if specified else
                ('General checks only; specification coverage not established' if selected else 'No checks or specifications recorded'),
            **count(selected)))
    candidate=identity.get('candidate') or {}; inv=coverage.get('inventory')
    context=dict(identity.get('report_context',{}));context.update((review or {}).get('report_context',{}))
    scene=dict(name=context.get('scene_name') or candidate.get('root') or identity.get('requested_candidate') or 'Scene identity unavailable',
        candidate=candidate.get('root') or identity.get('requested_candidate'),
        root_sha256=candidate.get('files',{}).get(candidate.get('root')),
        artifact_set_sha256=digest_json(candidate) if candidate else None,
        baseline=(identity.get('baseline') or {}).get('root'), inventory=inv,
        structure=(inv or {}).get('scene_structure'),evaluated_at_utc=core.get('runtime',{}).get('evaluated_at_utc'),
        intended_use=core.get('intended_use') or (review or {}).get('intended_use'),contract=core.get('contract_id'))
    return dict(schema_version='1.0',scene=scene,matrix=matrix,areas=area_rows,specifications=specs,checks=checks,
        specification_map_supplied=review is not None,
        human_specifications=sum(s['source']['provided_by']=='human' for s in specs),
        mapping_review=(review or {}).get('mapping_review'),
        notes=['Human source means explicitly recorded provenance, not authenticated authorship. No record does not prove no specification was provided elsewhere.',
               'Matrix counts selected checks once; required/advisory status is separate. Area/specification mappings may overlap.',
               'Warnings, missing evidence, execution errors and no-applicable subjects are not clean passes. Core admission/integrity checks are shown separately.',
               'Coverage extent is a caller declaration, not inferred from passing results. A missing specification map leaves full-intent coverage unknown.',
               'Simulation is an execution method, not a second copy of its check. Rendered appearance and physical calibration need suitable evidence.'])


def render_overview(data):
    scene=data['scene']; inv=scene['inventory'];structure=scene['structure']
    facts=[('Scene file',scene['candidate'] or 'Unavailable'),('Compared baseline',scene['baseline'] or 'None'),
           ('Use',scene['intended_use'] or 'Unrecorded'),('Run (UTC)',scene['evaluated_at_utc'] or 'Unrecorded')]
    if inv:
        facts += [('Observed structure',f"{inv['prims']} prims · {inv['meshes']} meshes · {inv['materials']} materials · {inv['layers']} USD layers · {inv['external_files']} external files"),
                  ('Motion / physics',f"{inv['animated_transform_prims']} prims with authored transform animation · {inv['rigid_bodies']} rigid bodies · {inv['colliders']} colliders")]
    else: facts.append(('Observed structure','Unavailable — admission did not complete or this older report did not record inventory'))
    if structure:
        facts += [('Coordinates',f"{structure['meters_per_unit']} m/unit ({'authored' if structure['units_authored'] else 'USD default'}); {structure['up_axis']}-up ({'authored' if structure['up_axis_authored'] else 'USD default'}); root {structure['default_prim']}"),
                  ('Saved clock',f"{structure['start_time_code']}–{structure['end_time_code']} at {structure['time_codes_per_second']} time codes/s" if structure['clock_authored'] else 'Clock/range not fully authored; no intended timing inferred')]
        if structure.get('rate_metadata'):
            facts.append(('Clock rate source', f"{structure['rate_metadata']} · {structure.get('rate_layer') or 'USD fallback'}"))
    info=''.join(f'<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>' for k,v in facts)
    hierarchy=''
    if structure:
        tree='\n'.join(f"{x['path']}  [{x['type']}]" for x in structure['hierarchy'])
        hierarchy=f'<details><summary>Scene hierarchy and revision</summary><pre>{E(tree)}</pre><p>{E(structure["hierarchy_scope"])}</p><p>Root SHA-256: <code>{E(scene["root_sha256"])}</code><br>Artifact set SHA-256: <code>{E(scene["artifact_set_sha256"])}</code></p></details>'
    matrix=''.join('<tr><th scope="row">'+E(x['label'])+f'<small>{x["required"]} required · {x["advisory"]} advisory</small></th>'+''.join(f'<td class="count-{k if x[k] else "zero"}">{x[k]}</td>' for k in ('pass','warning','fail','unknown','error','not_applicable'))+'</tr>' for x in data['matrix'])
    areas=''.join(f'<tr><th scope="row">{E(x["label"])}</th><td>{E(x["human_input"])}</td><td>{E(", ".join(SOURCE_LABELS[s] for s in x["specification_sources"]) or "No target recorded")}</td><td>{E(x["coverage"])}</td><td>{x["checks"]} checks: {x["pass"]} pass, {x["warning"]} warn, {x["fail"]} fail, {x["unknown"]} unknown, {x["error"]} error, {x["not_applicable"]} N/A</td></tr>' for x in data['areas'])
    specs=[]
    for s in data['specifications']:
        specs.append(f'<tr><td><strong>{E(s["statement"])}</strong><small>{E(s["id"])} · {"Required" if s["required"] else "Advisory"}</small></td><td>{E(SOURCE_LABELS[s["source"]["provided_by"]])}<small>{E(s["source"]["reference"])}</small></td><td>{E(s["coverage"])}<small>{s["completed_count"]}/{s["mapped_count"]} mapped checks produced assessed results; this is not a percentage of the whole brief.</small></td><td>{E(STATUS_LABELS.get(s["status"],s["status"]))}<small>{E(s["reason"])}</small><details><summary>Targets, measurements and coverage declaration</summary><p>{E(", ".join(s["check_ids"]) or "No automated check")}</p><p>{E(s["coverage_declaration"]["reason"])}</p><pre>{E(json.dumps(s["comparisons"],indent=2))}</pre></details></td></tr>')
    spec_table=('<div class="scroll"><table class="spec-table"><thead><tr><th>Specification / target</th><th>Supplied by</th><th>Specification coverage</th><th>Result and gap</th></tr></thead><tbody>'+''.join(specs)+'</tbody></table></div>') if specs else '<p>No task-specific specification is recorded. General checks can assess saved structure and delivery, but cannot establish whether the scene meets an unstated intent.</p>'
    human=f'{data["human_specifications"]} specification/target entries have a recorded human source.' if data['human_specifications'] else 'No human specification source is recorded in these inputs.'
    map_note='A declared requirement map was supplied.' if data['specification_map_supplied'] else 'No complete specification map was supplied; configured targets below are not a complete brief.'
    mapping=data.get('mapping_review'); map_note += (' Mapping review: '+mapping['status']+'.') if mapping else ''
    return f'''<section class="reader-overview"><h2>Scene under test: {E(scene['name'])}</h2><dl class="scene-facts">{info}</dl>{hierarchy}
<h2>Results at a glance</h2><p>{E(human)} {E(map_note)}</p>
<div class="scroll" tabindex="0" aria-label="Results by source of requirement"><table class="result-matrix"><thead><tr><th>Check category</th><th>Pass</th><th>Warn</th><th>Fail</th><th>Unknown / partial</th><th>Error</th><th>No applicable subjects</th></tr></thead><tbody>{matrix}</tbody></table></div>
<p class="reader-note">Counts are checks, not assets. A check can assess many objects or samples; those counts appear in the detailed results. General checks need no task-specific target. Specification checks use a recorded target or requirement mapping. A simulation can be one of these specification checks.</p>
<h2>Specifications and coverage by area</h2><div class="scroll"><table class="area-matrix"><thead><tr><th>Area</th><th>Human specification?</th><th>Other / recorded sources</th><th>Specification coverage</th><th>Check results</th></tr></thead><tbody>{areas}</tbody></table></div>
<h2>What each specification establishes</h2>{spec_table}
<p><a href="overview.json">Scene and coverage data</a> · <a href="result-matrix.csv">Summary matrix CSV</a> · <a href="specifications.csv">Specification coverage CSV</a></p>
<details><summary>How to read these categories and limits</summary><ul>{''.join('<li>'+E(x)+'</li>' for x in data['notes'])}</ul></details></section>'''


STYLE='''.reader-overview{margin:24px 0 36px}.reader-overview table{table-layout:auto}.reader-overview th:first-child{width:auto}.reader-overview th{white-space:normal}.reader-overview td{overflow-wrap:anywhere}.reader-overview small{display:block;font-weight:400;color:#51616d;margin-top:5px}.scene-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}.scene-facts>div{padding:12px 16px;background:white;border:1px solid #d6dee5;border-radius:6px}.scene-facts dt{font-size:12px;color:#526473}.scene-facts dd{margin:4px 0 0;overflow-wrap:anywhere}.reader-overview .result-matrix{min-width:740px}.reader-overview .result-matrix th:first-child{min-width:220px}.reader-overview .area-matrix{min-width:800px}.reader-overview .spec-table{min-width:800px}.reader-note{color:#526473;font-size:13px}.reader-overview .scroll{overflow:auto}.reader-overview pre{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:600px){.scene-facts{grid-template-columns:1fr}}'''
STYLE += '.count-pass{color:#21633f;font-weight:600}.count-fail,.count-error{color:#a02e25;font-weight:600}.count-warning,.count-unknown{color:#805916;font-weight:600}.count-zero{color:#64727c}'


def markdown_overview(data):
    def safe(v): return str(v).replace('|','\\|').replace('\n',' ')
    scene=data['scene']; inv=scene['inventory']
    lines=[f"## Scene under test: {safe(scene['name'])}",'',f"File: {safe(scene['candidate'])}. Use: {safe(scene['intended_use'])}."]
    if inv: lines += [f"Observed: {inv['prims']} prims, {inv['meshes']} meshes, {inv['materials']} materials, {inv['animated_transform_prims']} animated-transform prims, {inv['rigid_bodies']} rigid bodies."]
    else: lines += ['Scene inventory unavailable; counts are unknown.']
    lines += ['', '## Results at a glance', '', '| Check category | Pass | Warn | Fail | Unknown/partial | Error | N/A |','|---|---:|---:|---:|---:|---:|---:|']
    lines += ['| '+' | '.join(safe(x[k]) for k in ('label','pass','warning','fail','unknown','error','not_applicable'))+' |' for x in data['matrix']]
    lines += ['',f"Recorded human specification/target entries: {data['human_specifications']}. No record does not prove none were supplied elsewhere.",'',
              '## Specifications and coverage','','| Specification | Source | Coverage | Result |','|---|---|---|---|']
    lines += ['| '+' | '.join(safe(v) for v in (x['statement'],SOURCE_LABELS[x['source']['provided_by']],x['coverage'],STATUS_LABELS.get(x['status'],x['status'])))+' |' for x in data['specifications']]
    if not data['specifications']: lines+=['No task specification is recorded; full-intent coverage is unknown.']
    lines += ['',*data['notes'],'','[Overview JSON](overview.json) · [Results matrix](result-matrix.csv) · [Specification coverage](specifications.csv)','']
    return '\n'.join(lines)


def write_overview(data, out, csv_file, core_file='result.json'):
    (out/'overview.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    csv_file(out/'result-matrix.csv',['id','label','total','required','advisory',*STATUSES],data['matrix'])
    csv_file(out/'specifications.csv',['id','statement','source','source_reference','areas','required','coverage','mapped_count','completed_count','status','check_ids','reason','evidence_pointer','evidence_file'],[
        dict(s,source=s['source']['provided_by'],source_reference=s['source']['reference'],areas=', '.join(s['areas']),check_ids=', '.join(s['check_ids']),
             evidence_file='assessment.json' if s['declaration_kind']=='review-plan obligation' else core_file) for s in data['specifications']])
