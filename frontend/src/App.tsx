import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { BookOpen, Building2, CalendarDays, Check, ChevronRight, DoorOpen, Download, GraduationCap, LayoutDashboard, LoaderCircle, Plus, ShieldCheck, Sparkles, Upload, UsersRound, X } from 'lucide-react'
import { API_BASE, api, send, type Row } from './api'
import { validateEntry } from './validation'
import { COLLEGE_TIME_CONFIG, getSessionGridPosition, type TimetableSession } from './timetable'
import { buildS5Readiness, defaultCheckboxValue, getS5AssignmentOptions, getS5RequirementsForYear, hasLabCompatiblePeriod } from './s5Readiness.mjs'
import { validateGenerationResult } from './generation.mjs'
import { loadCollections, saveRecord } from './persistence.mjs'

type Section = 'overview' | 'timetable' | 'generate' | 'structure' | 'faculty' | 'rooms' | 'subjects' | 'groups' | 'import' | 's5-data' | 'configuration'
type Data = Record<string, Row[]>
const collections = ['departments', 'academic-years', 'semesters', 'student-groups', 'faculty', 'rooms', 'subjects', 'semester-subjects', 'faculty-subjects', 'shared-subject-requirements', 'section-teacher-assignments', 'college-time-configurations', 'college-working-days', 'college-time-blocks', 'room-capabilities', 'room-availability-profiles', 'room-availability-windows', 'faculty-scheduling-profiles', 'faculty-availability-windows', 'activity-room-requirements', 'activity-equipment-requirements']
const titles: Record<Section, string> = { overview: 'Overview', timetable: 'Timetable viewer', generate: 'Generate timetables', structure: 'Academic structure', faculty: 'Faculty management', rooms: 'Rooms and laboratories', subjects: 'Subject management', groups: 'Student groups', import: 'Excel import', 's5-data': 'S5 curriculum', configuration: 'Timetable configuration' }
const roomDataKinds: [string,string][] = [['room-capabilities','Equipment & capabilities'],['room-availability-profiles','Availability profiles'],['room-availability-windows','Availability windows']]
const weekdays: [string,string][] = [['0','Monday'],['1','Tuesday'],['2','Wednesday'],['3','Thursday'],['4','Friday'],['5','Saturday'],['6','Sunday']]

function App() {
  const [section, setSection] = useState<Section>('overview')
  const [data, setData] = useState<Data>({})
  const [loading, setLoading] = useState(true)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState<Row | null>(null)
  const [detail, setDetail] = useState<Row | null>(null)
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const values = await loadCollections((path) => api<Row[]>(path), collections)
      setData(values)
      setHasLoaded(true)
      setError('')
      return true
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load academic data.')
      return false
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])

  const counts = useMemo(() => ({ faculty: data.faculty?.length ?? 0, rooms: data.rooms?.length ?? 0, subjects: data.subjects?.length ?? 0, groups: data['student-groups']?.length ?? 0 }), [data])
  const navigate = (next: Section) => { setSection(next); setEditing(null); setDetail(null); setFormError(''); setNotice('') }

  async function save(event: FormEvent<HTMLFormElement>, kind: string, path: string, extra: Record<string, unknown> = {}) {
    event.preventDefault()
    const updating = /\/\d+$/.test(path)
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    const values = Object.fromEntries([...form.entries()].map(([key, value]) => [key, String(value).trim()]))
    formElement.querySelectorAll<HTMLInputElement>('input[type="checkbox"]').forEach((input) => { values[input.name] = String(input.checked) })
    for (const field of ['weekly_lecture_hours', 'weekly_tutorial_hours', 'weekly_practical_hours', 'weekly_lecture_sessions', 'weekly_tutorial_sessions', 'weekly_practical_sessions']) {
      if (values[field] === '') values[field] = kind === 'shared-subject-requirements' ? '' : '0'
    }
    const validationKind = ['faculty', 'rooms', 'subjects'].includes(kind) ? kind : ''
    const errors = validationKind ? validateEntry(validationKind, values) : {}
    if (Object.keys(errors).length) { setFormError(Object.values(errors).join(' ')); return }
    const payload: Record<string, unknown> = { ...values, ...extra }
    for (const field of ['department_id', 'academic_year_id', 'semester_number', 'semester_id', 'student_count', 'student_group_id', 'subject_id', 'requirement_id', 'faculty_id', 'configuration_id', 'profile_id', 'activity_requirement_id', 'weekday', 'version', 'sequence_number', 'period_number', 'quantity', 'academic_hour_minutes', 'max_daily_minutes', 'max_weekly_minutes', 'weekly_lecture_hours', 'weekly_tutorial_hours', 'weekly_practical_hours', 'weekly_lecture_sessions', 'weekly_tutorial_sessions', 'weekly_practical_sessions', 'lecture_session_minutes', 'tutorial_session_minutes', 'practical_session_minutes', 'capacity']) {
      if (field in payload && payload[field] !== '') payload[field] = Number(payload[field])
    }
    if ('email' in payload && !payload.email) payload.email = null
    for (const field of ['lecture_session_minutes', 'tutorial_session_minutes', 'practical_session_minutes', 'weekly_lecture_sessions', 'weekly_tutorial_sessions', 'weekly_practical_sessions', 'academic_hour_minutes', 'max_daily_minutes', 'max_weekly_minutes']) if (payload[field] === '') payload[field] = null
    if (kind === 'shared-subject-requirements') for (const field of ['weekly_lecture_hours', 'weekly_tutorial_hours', 'weekly_practical_hours']) if (payload[field] === '') payload[field] = null
    for (const field of ['period_number', 'label', 'quantity']) if (payload[field] === '') payload[field] = null
    setBusy(true); setFormError('')
    try {
      const reloaded = await saveRecord({
        persist: () => send(path, updating ? 'PATCH' : 'POST', payload),
        reset: () => { setEditing(null); formElement.reset() },
        onSaved: () => setNotice(updating ? 'Changes saved to the database.' : 'Record saved to the database.'),
        reload: refresh,
      })
      if (!reloaded) setNotice(updating
        ? 'Changes were saved to the database, but the latest records could not be reloaded. Retry loading before continuing.'
        : 'The record was saved to the database, but the latest records could not be reloaded. Retry loading before continuing.')
    } catch (cause) { setFormError(cause instanceof Error ? cause.message : 'Could not save this record.') }
    finally { setBusy(false) }
  }

  async function remove(collection: string, row: Row) {
    if (!window.confirm(`Delete this ${collection.replaceAll('-', ' ')} record? This cannot be undone.`)) return
    try { await api(`/${collection}/${row.id}`, { method: 'DELETE' }); setNotice('Record deleted.'); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete this record.') }
  }

  const nav: { id: Section; icon: typeof LayoutDashboard; label: string }[] = [
    { id: 'overview', icon: LayoutDashboard, label: 'Overview' }, { id: 'timetable', icon: CalendarDays, label: 'Timetables' }, { id: 'generate', icon: Sparkles, label: 'Generate options' }, { id: 'structure', icon: GraduationCap, label: 'Academic structure' },
    { id: 'faculty', icon: UsersRound, label: 'Faculty' }, { id: 'rooms', icon: DoorOpen, label: 'Rooms & labs' },
    { id: 'subjects', icon: BookOpen, label: 'Subjects' }, { id: 'configuration', icon: CalendarDays, label: 'College times' },
    { id: 'groups', icon: Building2, label: 'Student groups' }, { id: 'import', icon: Upload, label: 'Excel import' },
  ]

  return <div className="admin-shell">
    <aside className="admin-sidebar">
      <div className="admin-brand"><span className="brand-mark"><CalendarDays size={20} /></span><span>Campus<span className="brand-accent">Plan</span></span></div>
      <div className="campus-card"><div className="campus-icon"><GraduationCap size={20} /></div><div><strong>Saintgits College</strong><small>of Engineering · CSE</small></div></div>
      <div className="sidebar-caption">ADMINISTRATION</div>
      <nav className="admin-nav" aria-label="Administrator sections">{nav.map(({ id, icon: Icon, label }) => <button key={id} className={section === id ? 'selected' : ''} onClick={() => navigate(id)}><Icon size={17} /><span>{label}</span>{section === id && <ChevronRight size={15} />}</button>)}</nav>
      <div className="sidebar-note"><ShieldCheck size={17} /><strong>Local prototype</strong><p>No login yet. Administrator controls are not protected for public use.</p></div>
      <div className="sidebar-school"><div className="mini-avatar">CSE</div><span><strong>CSE Department</strong><small>Saintgits College</small></span></div>
    </aside>
    <main className="admin-main">
      <header className="admin-topbar"><div><span className="top-crumb">Administrator workspace</span><span className="crumb-divider">/</span><strong>{titles[section]}</strong></div><span className="prototype-pill"><span /> Local data workspace</span></header>
      <div className="admin-content">
        {hasLoaded && error && <div className="alert error-alert"><span>Could not refresh records. Showing the last successfully loaded data. {error}</span><button onClick={() => void refresh()}>Retry</button></div>}
        {notice && <div className="alert success-alert"><Check size={16} />{notice}<button aria-label="Dismiss" onClick={() => setNotice('')}><X size={15} /></button></div>}
        {loading && !hasLoaded ? <div className="loading-state"><LoaderCircle className="spin" /> Loading academic data…</div> : !hasLoaded ? <div className="panel empty-state" role="alert"><strong>Could not load saved data</strong><p>{error || 'The backend did not return the saved records. Your database has not been changed.'}</p><button className="primary-button" onClick={() => void refresh()}>Retry loading</button></div> : <>
          {section === 'overview' && <Overview counts={counts} groups={data['student-groups'] ?? []} semesters={data.semesters ?? []} years={data['academic-years'] ?? []} go={navigate} />}
          {section === 'timetable' && <TimetableView data={data} />}
          {section === 'generate' && <TimetableGenerator data={data} />}
          {section === 'structure' && <Structure data={data} onSave={save} editing={editing} setEditing={setEditing} formError={formError} busy={busy} />}
          {section === 'faculty' && <><ResourceSection kind="faculty" title="Faculty management" description="Add and maintain teaching staff records." rows={data.faculty ?? []} editing={editing} setEditing={setEditing} detail={detail} setDetail={setDetail} onSave={save} onDelete={remove} formError={formError} busy={busy} /><DataManager title="Faculty availability and workload" description="Enter confirmed available windows and daily/weekly workload limits. Unconfirmed profiles are not treated as unrestricted." kinds={facultyDataKinds} data={data} editing={editing} setEditing={setEditing} onSave={save} onDelete={remove} formError={formError} busy={busy} /></>}
          {section === 'rooms' && <><ResourceSection kind="rooms" title="Rooms and laboratories" description="Record actual room identifiers, types and capacities. S5 sections have 72 students and the confirmed classroom capacity is 75; no room records are preloaded." rows={data.rooms ?? []} editing={editing} setEditing={setEditing} detail={detail} setDetail={setDetail} onSave={save} onDelete={remove} formError={formError} busy={busy} /><RoomReadiness data={data} /><DataManager title="Room equipment and availability" description="Enter room equipment, capabilities and explicit availability details." kinds={roomDataKinds} data={data} editing={editing} setEditing={setEditing} onSave={save} onDelete={remove} formError={formError} busy={busy} /></>}
          {section === 'subjects' && <Subjects data={data} editing={editing} setEditing={setEditing} onSave={save} onDelete={remove} formError={formError} busy={busy} />}
          {section === 's5-data' && <S5Requirements data={data} editing={editing} setEditing={setEditing} onSave={save} onDelete={remove} formError={formError} busy={busy} refresh={refresh} />}
          {section === 'configuration' && <ConfigurationPage data={data} editing={editing} setEditing={setEditing} onSave={save} onDelete={remove} formError={formError} busy={busy} />}
          {section === 'groups' && <Groups data={data} onSave={save} editing={editing} setEditing={setEditing} onDelete={remove} formError={formError} busy={busy} />}
          {section === 'import' && <ImportSection onImported={refresh} />}
        </>}
        <footer className="admin-footer">AI College Timetable Generator <span>•</span> CSE data management <span>•</span> No timetable has been generated</footer>
      </div>
    </main>
  </div>
}

function TimetableView({ data }: { data: Data }) {
  const [semesterCode, setSemesterCode] = useState('S1')
  const [groupId, setGroupId] = useState('all')
  const [official, setOfficial] = useState<{version:number;published_at:string;sessions:GeneratedSession[];configuration:{working_days:number[];blocks:Row[]}}|null>(null)
  const [officialLoading, setOfficialLoading] = useState(false)
  const semesterNumber = Number(semesterCode.slice(1))
  const cseDepartmentIds = new Set((data.departments ?? []).filter((department) => department.code === 'CSE').map((department) => department.id))
  const semester = (data.semesters ?? []).find((record) => record.semester_number === semesterNumber && cseDepartmentIds.has(Number(record.department_id)))
  const semesterGroups = (data['student-groups'] ?? []).filter((group) => group.semester_id === semester?.id)
  const selectedGroup = semesterGroups.find((group) => String(group.id) === groupId)
  const curriculum = (data['semester-subjects'] ?? []).filter((assignment) => assignment.semester_id === semester?.id && (groupId === 'all' || assignment.student_group_id === selectedGroup?.id))
  const facultyAssignments = data['faculty-subjects'] ?? []
  const subjects = data.subjects ?? []
  const faculty = data.faculty ?? []

  useEffect(() => { setGroupId('all') }, [semesterCode])
  useEffect(() => {
    let active=true
    setOfficial(null)
    if(semesterNumber!==5||!semester){setOfficialLoading(false);return ()=>{active=false}}
    setOfficialLoading(true)
    void api<Array<{version:number;published_at:string;sessions:GeneratedSession[];configuration:{working_days:number[];blocks:Row[]}}>>(`/timetables/official?academic_year_id=${semester.academic_year_id}`)
      .then((rows)=>{if(active)setOfficial(rows.find((row)=>row.sessions.some((session)=>session.group_name==='S5-A'||session.group_name==='S5-B'))??null)})
      .catch(()=>{if(active)setOfficial(null)})
      .finally(()=>{if(active)setOfficialLoading(false)})
    return ()=>{active=false}
  },[semesterNumber,semester?.id])
  const activeConfig=(data['college-time-configurations']??[]).find((config)=>config.is_active)
  const periods=official?.configuration.blocks.filter((block)=>block.block_type==='teaching').sort((a,b)=>Number(a.sequence_number)-Number(b.sequence_number))??(data['college-time-blocks']??[]).filter((block)=>block.configuration_id===activeConfig?.id&&block.block_type==='teaching').sort((a,b)=>Number(a.sequence_number)-Number(b.sequence_number))
  const workingDays=official?.configuration.working_days??(data['college-working-days']??[]).filter((day)=>day.configuration_id===activeConfig?.id).map((day)=>Number(day.weekday)).sort((a,b)=>a-b)
  const publishedSessions=official?.sessions.filter((session)=>groupId==='all'||session.group_id===Number(groupId))??[]

  return <>
    <PageIntro eyebrow="CSE DEPARTMENT · WEEKLY VIEW" title="Timetable viewer" description="Browse the same college day layout for S1, S3, S5, and S7. No timetable entries are fabricated." action={<span className="format-pill">View only</span>} />
    <section className="panel timetable-view-panel">
      <div className="timetable-view-controls">
        <div className="semester-selector" role="group" aria-label="Select CSE semester">
          {[1, 3, 5, 7].map((number) => {
            const code = `S${number}`
            return <button key={code} aria-pressed={semesterCode === code} className={semesterCode === code ? 'selected' : ''} onClick={() => setSemesterCode(code)}>{code}</button>
          })}
        </div>
        <label className="group-selector"><span>Student group</span><select value={groupId} onChange={(event) => setGroupId(event.target.value)}><option value="all">All groups</option>{semesterGroups.map((group) => <option key={group.id} value={group.id}>{String(group.group_name)} · {String(group.student_count)} students{group.is_predefined ? ' · predefined' : ''}</option>)}</select></label>
      </div>
      <div className="selected-semester-heading"><div><div className="section-eyebrow">CSE · {semesterCode}</div><h2>{String(semester?.name ?? `Semester ${semesterNumber}`)}</h2><p>{semester ? `${semesterGroups.length} student group${semesterGroups.length === 1 ? '' : 's'} configured` : 'This semester is not configured in academic data yet.'}</p></div><span className="schedule-status"><i />{official?`Published · version ${official.version}`:'No published schedule'}</span></div>
      <div className="shared-time-note"><CalendarDays size={15} /><span><strong>Shared college day layout</strong><small>One period sequence and lunch break are used for every semester. Clock times are not configured in the available project data.</small></span></div>
      {official&&semesterNumber===5?<>{(['S5-A','S5-B'] as const).filter((group)=>groupId==='all'||official.sessions.some((session)=>session.group_name===group&&session.group_id===Number(groupId))).map((group)=><section className="generated-group-preview" key={group}><h4>{group}<span>Official · v{official.version}</span></h4><SchedulePreview sessions={publishedSessions.filter((session)=>session.group_name===group)} periods={periods} workingDays={workingDays}/></section>)}<p className="timetable-muted-empty">Published {new Date(official.published_at).toLocaleString()}</p></>:<ScheduleGrid sessions={[]} />}
      {!official&&<div className="timetable-empty-notice"><CalendarDays size={19} /><div><strong>{officialLoading?'Checking official timetable…':'No timetable published for this semester yet.'}</strong><p>Only a published official version appears in this viewer.</p></div></div>}
    </section>
    <section className="timetable-info-grid">
      <div className="panel"><div className="panel-heading"><div><div className="section-eyebrow">ACADEMIC DATA</div><h2>Subjects and weekly requirements</h2><p>{groupId === 'all' ? 'Configured for this semester across all groups.' : `Configured for ${String(selectedGroup?.group_name ?? 'the selected group')}.`}</p></div></div>
        {curriculum.length === 0 ? <p className="timetable-muted-empty">No subject assignments are available for {semesterCode} yet.</p> : <div className="timetable-subject-list">{curriculum.map((assignment) => {
          const subject = subjects.find((record) => record.id === assignment.subject_id)
          const group = semesterGroups.find((record) => record.id === assignment.student_group_id)
          const teachers = facultyAssignments.filter((link) => link.semester_subject_id === assignment.id).map((link) => faculty.find((record) => record.id === link.faculty_id)).filter((record): record is Row => Boolean(record))
          return <article className="timetable-subject-item" key={assignment.id}><span className="subject-code-chip">{String(subject?.subject_code ?? '—')}</span><div><strong>{String(subject?.subject_name ?? 'Subject details unavailable')}</strong><small>{String(group?.group_name ?? 'Group')} · {Number(assignment.weekly_lecture_hours) + Number(assignment.weekly_tutorial_hours) + Number(assignment.weekly_practical_hours)} weekly hours</small><small>{teachers.length ? teachers.map((teacher) => String(teacher.faculty_name)).join(', ') : 'Faculty not assigned'}</small></div></article>
        })}</div>}
      </div>
      <div className="panel"><div className="panel-heading"><div><div className="section-eyebrow">AVAILABLE FACULTY</div><h2>Faculty directory</h2><p>Names come from saved faculty records.</p></div><span className="count-badge">{faculty.length}</span></div>
        {faculty.length === 0 ? <p className="timetable-muted-empty">No faculty records available yet.</p> : <div className="timetable-faculty-list">{faculty.map((member) => <div key={member.id}><span className="faculty-dot">{String(member.faculty_name ?? '?').slice(0, 1)}</span><span><strong>{String(member.faculty_name)}</strong><small>{String(member.faculty_code)}{member.is_active ? '' : ' · inactive'}</small></span></div>)}</div>}
      </div>
    </section>
  </>
}

type GeneratedSession = {
  group_id: number; group_name: string; subject_code: string; subject_name: string;
  activity_type: 'lecture' | 'tutorial' | 'practical'; session_index: number;
  teacher_id: number; teacher_name: string; room_id: number; room_name: string;
  weekday: number; period_numbers: number[]; start_time: string; end_time: string;
  duration_minutes: number;
}
type GenerationResult = {
  status: 'success' | 'incomplete' | 'infeasible' | 'invalid'; requested_count: number;
  valid_count: number; alternatives: { alternative_number: number; sessions: GeneratedSession[]; validation: string }[];
  diagnostics: string[]; warnings: string[];
}
type ApprovedTimetable = { id:number; academic_year_id:number; semester_id:number; semester_number:number; version:number; status:string; alternative_number:number; sessions_json:GeneratedSession[]; approved_at:string }

function TimetableGenerator({data}:{data:Data}) {
  const [academicYearId,setAcademicYearId]=useState('')
  const [requested,setRequested]=useState('4')
  const [result,setResult]=useState<GenerationResult|null>(null)
  const [activeAlternative,setActiveAlternative]=useState(0)
  const [comparing,setComparing]=useState(false)
  const [busy,setBusy]=useState(false)
  const [progress,setProgress]=useState('')
  const [approvals,setApprovals]=useState<ApprovedTimetable[]>([])
  const [officialIds,setOfficialIds]=useState<number[]>([])
  const [workflowMessage,setWorkflowMessage]=useState('')
  const departments=data.departments??[]
  const cseIds=new Set(departments.filter((department)=>(department.code==='CSE'||department.name==='CSE')).map((department)=>String(department.id)))
  const s5Semesters=(data.semesters??[]).filter((semester)=>Number(semester.semester_number)===5&&cseIds.has(String(semester.department_id)))
  const years=(data['academic-years']??[]).filter((year)=>s5Semesters.some((semester)=>String(semester.academic_year_id)===String(year.id)))
  const selectedYear=years.find((year)=>String(year.id)===academicYearId)??years.find((year)=>year.is_active)??years[0]
  const activeConfig=(data['college-time-configurations']??[]).find((config)=>config.is_active)
  const blocks=(data['college-time-blocks']??[]).filter((block)=>block.configuration_id===activeConfig?.id).sort((a,b)=>Number(a.sequence_number)-Number(b.sequence_number))
  const periods=blocks.filter((block)=>block.block_type==='teaching')
  const workingDays=(data['college-working-days']??[]).filter((day)=>day.configuration_id===activeConfig?.id).map((day)=>Number(day.weekday)).sort((a,b)=>a-b)
  const alternative=result?.alternatives[activeAlternative]
  useEffect(()=>{
    let active=true
    setApprovals([]);setOfficialIds([])
    if(!selectedYear)return ()=>{active=false}
    void Promise.all([
      api<ApprovedTimetable[]>(`/timetables/approved?academic_year_id=${selectedYear.id}`),
      api<Array<{snapshot_id:number}>>(`/timetables/official?academic_year_id=${selectedYear.id}`),
    ]).then(([saved,current])=>{if(active){setApprovals(saved);setOfficialIds(current.map((row)=>row.snapshot_id))}}).catch(()=>{if(active){setApprovals([]);setOfficialIds([])}})
    return ()=>{active=false}
  },[selectedYear?.id])
  async function generate(){
    if(!selectedYear)return
    setBusy(true);setProgress('Checking required information…');setResult(null);setActiveAlternative(0);setComparing(false)
    const messages=['Checking required information…','Building the constraint model…','Searching for distinct valid schedules…']
    let index=0
    const timer=window.setInterval(()=>{index=(index+1)%messages.length;setProgress(messages[index])},1100)
    try{
      const response=await api<GenerationResult>('/timetables/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({academic_year_id:Number(selectedYear.id),number_of_alternatives:Number(requested)})})
      setResult(validateGenerationResult(response))
    }catch(error){setResult({status:'incomplete',requested_count:Number(requested),valid_count:0,alternatives:[],diagnostics:[error instanceof Error?error.message:'The timetable request failed.'],warnings:[]})}
    finally{window.clearInterval(timer);setBusy(false);setProgress('')}
  }
  async function approveSelected(){
    if(!selectedYear||!alternative||alternative.validation!=='valid'||result?.status!=='success')return
    if(!window.confirm(`Approve Alternative ${alternative.alternative_number} as an immutable S5 timetable snapshot?`))return
    setWorkflowMessage('Revalidating and saving the approval…')
    try{
      await api<ApprovedTimetable>('/timetables/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({academic_year_id:Number(selectedYear.id),alternative_number:alternative.alternative_number,sessions:alternative.sessions,confirm_approval:true})})
      const saved=await api<ApprovedTimetable[]>(`/timetables/approved?academic_year_id=${selectedYear.id}`)
      setApprovals(saved);setWorkflowMessage('Approval saved. It is not published yet.')
    }catch(error){setWorkflowMessage(error instanceof Error?error.message:'Approval failed. Generate a fresh alternative and retry.')}
  }
  async function publishApproved(snapshot:ApprovedTimetable){
    if(!window.confirm(`Publish approved timetable version ${snapshot.version}? The current official version will remain in publication history.`))return
    setWorkflowMessage('Switching the official timetable…')
    try{
      await api(`/timetables/${snapshot.id}/publish`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm_publish:true})})
      const current=await api<Array<{snapshot_id:number}>>(`/timetables/official?academic_year_id=${snapshot.academic_year_id}`)
      setOfficialIds(current.map((row)=>row.snapshot_id));setWorkflowMessage(`Version ${snapshot.version} is now the official published timetable.`)
    }catch(error){setWorkflowMessage(error instanceof Error?error.message:'Publishing failed. Refresh and retry.')}
  }
  const compareRows=useMemo(()=>{
    const rows=new Map<string,{label:string;placements:Map<number,string>}>()
    for(const alternative of result?.alternatives??[])for(const session of alternative.sessions){
      const key=[session.group_name,session.subject_code,session.activity_type,session.session_index].join('|')
      const day=weekdays.find(([value])=>Number(value)===session.weekday)?.[1]??String(session.weekday)
      const last=session.period_numbers[session.period_numbers.length-1]
      const placement=`${day} · P${session.period_numbers[0]}${last!==session.period_numbers[0]?`–P${last}`:''} · ${session.teacher_name} · ${session.room_name}`
      const row=rows.get(key)??{label:`${session.group_name} · ${session.subject_code} · ${session.activity_type} ${session.session_index}`,placements:new Map<number,string>()}
      row.placements.set(alternative.alternative_number,placement);rows.set(key,row)
    }
    return [...rows.values()]
  },[result])
  return <>
    <PageIntro eyebrow="CSE · SEMESTER 5" title="Generate timetable alternatives" description="The CP-SAT constraint solver schedules S5-A and S5-B together and checks their shared teachers and rooms." action={<span className="format-pill">Constraint solver · OR-Tools</span>} />
    <div className="shared-time-note"><Sparkles size={16}/><span><strong>Complete information is required</strong><small>Unconfirmed hours, durations, teacher availability, workload limits, room requirements, or room availability block generation. The solver does not fill missing values.</small></span></div>
    <section className="panel" style={{marginBottom:18}}><div className="generation-controls"><label className="form-field"><span>Academic year</span><select value={selectedYear?.id??''} onChange={(event)=>{setAcademicYearId(event.target.value);setResult(null)}}><option value="">Choose a CSE S5 academic year</option>{years.map((year)=><option key={String(year.id)} value={String(year.id)}>{String(year.name)}{year.is_active?' · active':''}</option>)}</select></label><label className="form-field"><span>Alternatives to find</span><select value={requested} onChange={(event)=>setRequested(event.target.value)}><option value="4">4 alternatives</option><option value="3">3 alternatives</option></select></label><button className="primary-button" disabled={!selectedYear||busy} onClick={()=>void generate()}>{busy?<><LoaderCircle className="spin" size={15}/> Generating…</>:<><Sparkles size={15}/> Generate alternatives</>}</button></div>{busy&&<p className="generation-progress" role="status">{progress}</p>}{!years.length&&<p className="form-error" role="status">Set up the CSE department, an academic year, and its S5 semester first.</p>}</section>
    <div className="generation-safety-note"><ShieldCheck size={16}/><span>Results are previews only. Generating does not save, approve, or publish schedules and cannot replace an official timetable.</span></div>
    {result&&<>
      <section className="panel generation-result-panel"><div className="panel-heading"><div><div className="section-eyebrow">GENERATION RESULT</div><h2>{result.valid_count} valid alternative{result.valid_count===1?'':'s'} found</h2><p>{result.status==='success'?'Every displayed alternative passed independent validation.':result.status==='infeasible'?'No complete valid schedule satisfies the confirmed constraints.':result.status==='invalid'?'A result failed independent validation and was withheld.':'Generation is blocked until required data is completed.'}</p></div>{result.alternatives.length>1&&<button className="quiet-button" onClick={()=>setComparing(!comparing)}>{comparing?'View selected preview':'Compare alternatives'}</button>}</div>
        {result.diagnostics.length>0&&<ul className="generation-diagnostics" role="status">{result.diagnostics.map((message,index)=><li key={index}>{message}</li>)}</ul>}
        {result.warnings.length>0&&<details className="generation-warnings"><summary>{result.warnings.length} resource warning(s)</summary><ul>{result.warnings.map((message,index)=><li key={index}>{message}</li>)}</ul></details>}
        {result.alternatives.length>0&&!comparing&&<><div className="alternative-tabs" role="tablist" aria-label="Timetable alternatives">{result.alternatives.map((item,index)=><button key={item.alternative_number} role="tab" aria-selected={activeAlternative===index} className={activeAlternative===index?'selected':''} onClick={()=>setActiveAlternative(index)}>Alternative {item.alternative_number} <Check size={13}/></button>)}</div>{alternative&&<div className="alternative-preview"><h3>Alternative {alternative.alternative_number} · independently validated · selected</h3>{(['S5-A','S5-B'] as const).map((group)=><section key={group} className="generated-group-preview"><h4>{group} <span>72 students</span></h4><SchedulePreview sessions={alternative.sessions.filter((session)=>session.group_name===group)} periods={periods} workingDays={workingDays}/></section>)}<button className="primary-button" disabled={result.status!=='success'||alternative.validation!=='valid'} onClick={()=>void approveSelected()}><ShieldCheck size={15}/> Approve selected alternative</button></div>}</>}
        {result.alternatives.length>1&&comparing&&<div className="table-wrap alternative-comparison"><table><thead><tr><th>Required session</th>{result.alternatives.map((item)=><th key={item.alternative_number}>Alternative {item.alternative_number}</th>)}</tr></thead><tbody>{compareRows.map((row)=><tr key={row.label}><th>{row.label}</th>{result.alternatives.map((item)=><td key={item.alternative_number}>{row.placements.get(item.alternative_number)??'—'}</td>)}</tr>)}</tbody></table></div>}
      </section>
    </>}
    {workflowMessage&&<p className="generation-progress" role="status">{workflowMessage}</p>}
    <section className="panel generation-result-panel"><div className="panel-heading"><div><div className="section-eyebrow">APPROVED VERSIONS</div><h2>Approval and publication</h2><p>Approvals are immutable snapshots. Publishing is a separate action; older versions remain in history.</p></div></div>{approvals.length===0?<p className="timetable-muted-empty">No approved timetable snapshots for this academic year.</p>:<div className="table-wrap alternative-comparison"><table><thead><tr><th>Version</th><th>Approved</th><th>Status</th><th>Action</th></tr></thead><tbody>{approvals.map((snapshot)=><tr key={snapshot.id}><th>v{snapshot.version} · Alternative {snapshot.alternative_number}</th><td>{new Date(snapshot.approved_at).toLocaleString()}</td><td>{officialIds.includes(snapshot.id)?'Officially published':'Approved · unpublished'}</td><td>{officialIds.includes(snapshot.id)?'Current official version':<button className="quiet-button" onClick={()=>void publishApproved(snapshot)}>Publish this version</button>}</td></tr>)}</tbody></table></div>}</section>
  </>
}

function SchedulePreview({sessions,periods,workingDays}:{sessions:GeneratedSession[];periods:Row[];workingDays:number[]}){
  if(!periods.length||!workingDays.length)return <p className="timetable-muted-empty">The active college period configuration is not available for preview.</p>
  return <div className="timetable-scroll"><table className="weekly-timetable generated-timetable"><thead><tr><th className="weekday-column">Weekday</th>{periods.map((period)=><th key={period.id}><span>Period {String(period.period_number)}</span><small>{String(period.start_time).slice(0,5)}–{String(period.end_time).slice(0,5)}</small></th>)}</tr></thead><tbody>{workingDays.map((weekday)=>{const cells=periods.map((period)=>{
    const currentNumber=Number(period.period_number)
    const session=sessions.find((item)=>item.weekday===weekday&&item.period_numbers[0]===currentNumber)
    if(session){const span=session.period_numbers.length;return <td className="session-cell" colSpan={span} key={`s-${session.subject_code}-${currentNumber}`}><div className={`timetable-session-card ${session.activity_type==='practical'?'lab-session-card':''}`}><strong>{session.subject_code} · {session.subject_name}</strong><small>{session.activity_type} · {session.teacher_name}</small><small>{session.room_name} · {session.start_time}–{session.end_time}</small>{span>1&&<span>Lab · {span} consecutive periods</span>}</div></td>}
    const covered=sessions.some((item)=>item.weekday===weekday&&item.period_numbers.length>1&&currentNumber>item.period_numbers[0]&&currentNumber<=item.period_numbers[item.period_numbers.length-1])
    return covered?null:<td className="blank-period-cell" key={`p-${period.id}`}><span>—</span></td>
  });return <tr key={weekday}><th scope="row" className="weekday-name">{weekdays.find(([value])=>Number(value)===weekday)?.[1]??String(weekday)}</th>{cells}</tr>})}</tbody></table></div>
}

function ScheduleGrid({ sessions }: { sessions: TimetableSession[] }) {
  const periodColumns = COLLEGE_TIME_CONFIG.teachingPeriods.map((period) => ({ kind: 'period' as const, period }))
  const columns = [...periodColumns.slice(0, COLLEGE_TIME_CONFIG.lunchAfterPeriod), { kind: 'lunch' as const }, ...periodColumns.slice(COLLEGE_TIME_CONFIG.lunchAfterPeriod)]
  return <div className="timetable-scroll"><table className="weekly-timetable"><thead><tr><th className="weekday-column">Weekday</th>{columns.map((column) => column.kind === 'lunch' ? <th className="lunch-heading" key="lunch">Lunch</th> : <th key={`p-${column.period}`}><span>Period {column.period}</span><small>P{column.period}</small></th>)}</tr></thead><tbody>{COLLEGE_TIME_CONFIG.weekdays.map((weekday) => {
    const daySessions = sessions.filter((session) => session.weekday === weekday)
    const cells = columns.map((column) => {
      if (column.kind === 'lunch') return <td className="lunch-cell" key="lunch"><span>Lunch break</span></td>
      const session = daySessions.find((item) => item.startPeriod === column.period)
      if (session) {
        const position = getSessionGridPosition(session)
        if (position && position.span > 1) {
          const cell = <td className="session-cell" colSpan={position.span} key={`session-${session.startPeriod}`}><SessionCard session={session} /></td>
          return cell
        }
        return <td className="session-cell" key={`session-${session.startPeriod}`}><SessionCard session={session} /></td>
      }
      // The period covered by a prior two-period session was rendered as part of that block.
      const covered = daySessions.some((item) => {
        const position = getSessionGridPosition(item)
        return position && position.span > 1 && column.period > item.startPeriod && column.period < item.startPeriod + item.durationPeriods
      })
      if (covered) return null
      return <td className="blank-period-cell" key={`empty-${column.period}`}><span>—</span></td>
    })
    return <tr key={weekday}><th scope="row" className="weekday-name">{weekday}</th>{cells}</tr>
  })}</tbody></table></div>
}

function SessionCard({ session }: { session: TimetableSession }) {
  return <div className={`timetable-session-card ${session.kind === 'laboratory' ? 'lab-session-card' : ''}`}><strong>{session.subject}</strong>{session.faculty && <small>{session.faculty}</small>}{session.room && <small>{session.room}</small>}{session.kind === 'laboratory' && <span>Laboratory · 2 periods</span>}</div>
}

function PageIntro({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-intro"><div><div className="section-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

function Overview({ counts, groups, semesters, years, go }: { counts: Record<string, number>; groups: Row[]; semesters: Row[]; years: Row[]; go: (section: Section) => void }) {
  const configured = [1, 3, 5, 7].map((number) => semesters.find((item) => item.semester_number === number))
  return <>
    <PageIntro eyebrow="CSE DEPARTMENT · SAINTGITS COLLEGE OF ENGINEERING" title="Academic data workspace" description="Add and review the source information used to prepare college timetables." action={<div className="admin-mode-label"><ShieldCheck size={16} /> Administrator Mode</div>} />
    <div className="prototype-banner"><span className="banner-light" /><div><strong>Phase 3 · Data management</strong><p>Enter confirmed academic information. Empty sections are expected in a new workspace.</p></div><span className="prototype-tag">Local prototype</span></div>
    <div className="metric-grid">{([
      ['Faculty', counts.faculty, UsersRound, 'faculty'], ['Rooms & labs', counts.rooms, DoorOpen, 'rooms'], ['Subjects', counts.subjects, BookOpen, 'subjects'], ['Student groups', counts.groups, Building2, 'groups'],
    ] as [string, number, typeof UsersRound, Section][]).map(([label, count, Glyph, destination]) => <button className="metric-card" key={label} onClick={() => go(destination)}><span className="metric-icon"><Glyph size={19} /></span><span className="metric-count">{count}</span><span className="metric-label">{label}</span><span className="metric-foot">{count ? 'Records entered' : 'Nothing added yet'}<ChevronRight size={14} /></span></button>)}</div>
    <section className="panel semester-panel"><div className="panel-heading"><div><div className="section-eyebrow">ACADEMIC STRUCTURE</div><h2>Configured semesters</h2><p>Semesters are linked to an academic year and department.</p></div><button className="quiet-button" onClick={() => go('structure')}>Manage structure <ChevronRight size={15} /></button></div>
      <div className="semester-tiles">{configured.map((semester, index) => { const semNumber = [1,3,5,7][index]; const groupCount = groups.filter((g) => g.semester_id === semester?.id).length; return <div className="semester-tile" key={semNumber}><span className={`sem-bubble bubble-${index}`}>S{semNumber}</span><div><strong>Semester {semNumber}</strong><small>{semester ? `${groupCount} configured group${groupCount === 1 ? '' : 's'}` : 'Not configured yet'}</small></div><span className={semester ? 'record-status active-status' : 'record-status'}>{semester ? 'Active' : 'Pending'}</span></div> })}</div>
      {years.length === 0 && <div className="inline-guidance">Start by adding an academic year in <button onClick={() => go('structure')}>Academic structure</button>.</div>}
    </section>
    <section className="getting-started"><div className="getting-icon"><BookOpen size={19} /></div><div><strong>Ready for your first data entry?</strong><p>Use the forms for one record at a time, or download a template to preview a spreadsheet before importing it.</p></div><button className="primary-button" onClick={() => go('import')}>Open Excel import <ChevronRight size={15} /></button></section>
  </>
}

function inputFields(kind: string, data: Data) {
  const field = (name: string, label: string, type = 'text', required = true, options?: [string, string][]) => ({ name, label, type, required, options })
  if (kind === 'faculty') return [field('faculty_name','Faculty name'), field('faculty_code','Faculty code'), field('email','Email','email',false), field('is_active','Active','checkbox',false)]
  if (kind === 'rooms') return [field('room_name','Room name'), field('room_type','Room type','select',true,[['classroom','Classroom'],['laboratory','Laboratory'],['other','Other']]), field('capacity','Capacity','number'), field('is_active','Active','checkbox',false)]
  if (kind === 'subjects') return [field('subject_code','Subject code'), field('subject_name','Subject name'), field('is_active','Active','checkbox',false)]
  if (kind === 'departments') return [field('name','Department name'),field('code','Department code')]
  if (kind === 'academic-years') return [field('name','Academic year'),field('start_date','Start date','date'),field('end_date','End date','date')]
  if (kind === 'semesters') return [field('department_id','Department','select',true,(data.departments ?? []).map((r) => [String(r.id),`${r.name} (${r.code})`] as [string,string])),field('academic_year_id','Academic year','select',true,(data['academic-years'] ?? []).map((r) => [String(r.id),String(r.name)] as [string,string])),field('semester_number','Semester number','number'),field('name','Semester label')]
  if (kind === 'student-groups') return [field('semester_id','Semester','select',true,(data.semesters ?? []).map((r) => [String(r.id),String(r.name)] as [string,string])),field('group_name','Group name'),field('section_identifier','Section identifier','text',false),field('student_count','Student count','number')]
  if (kind === 'semester-subjects') return [field('semester_id','Semester','select',true,(data.semesters ?? []).map((r) => [String(r.id),String(r.name)] as [string,string])),field('student_group_id','Student group','select',true,(data['student-groups'] ?? []).map((r) => [String(r.id),`${r.group_name} · ${r.student_count} students`] as [string,string])),field('subject_id','Subject','select',true,(data.subjects ?? []).map((r) => [String(r.id),`${r.subject_code} · ${r.subject_name}`] as [string,string])),field('weekly_lecture_hours','Weekly lecture hours','number',false),field('weekly_tutorial_hours','Weekly tutorial hours','number',false),field('weekly_practical_hours','Weekly practical hours','number',false),field('lecture_session_minutes','Lecture session minutes','number',false),field('tutorial_session_minutes','Tutorial session minutes','number',false),field('practical_session_minutes','Practical session minutes','number',false)]
  return [field('faculty_id','Faculty','select',true,(data.faculty ?? []).map((r) => [String(r.id),`${r.faculty_name} (${r.faculty_code})`] as [string,string])),field('semester_subject_id','Group subject assignment','select',true,(data['semester-subjects'] ?? []).map((r) => [String(r.id),`${data.subjects?.find((s) => s.id === r.subject_id)?.subject_code ?? 'Subject'} · ${data['student-groups']?.find((g) => g.id === r.student_group_id)?.group_name ?? 'Group'}`] as [string,string]))]
}

function extraInputFields(kind: string, data: Data, academicYearId = '') {
  const field = (name: string, label: string, type = 'text', required = true, options?: [string, string][]) => ({ name, label, type, required, options })
  const weekdayOptions: [string, string][] = [['0','Monday'],['1','Tuesday'],['2','Wednesday'],['3','Thursday'],['4','Friday'],['5','Saturday'],['6','Sunday']]
  if (kind === 'shared-subject-requirements') return [
    field('semester_id','CSE S5 semester','select',true,(data.semesters ?? []).filter((r) => r.semester_number === 5 && data.departments?.some((d) => d.id === r.department_id && d.code === 'CSE')).map((r) => [String(r.id),String(r.name)] as [string,string])),
    field('subject_id','Subject','select',true,(data.subjects ?? []).map((r) => [String(r.id),String(r.subject_code) + ' · ' + String(r.subject_name)] as [string,string])),
    field('weekly_lecture_hours','Weekly lecture hours · blank means unconfirmed','number',false),
    field('weekly_tutorial_hours','Weekly tutorial hours · blank means unconfirmed','number',false),
    field('weekly_practical_hours','Weekly practical hours · blank means unconfirmed','number',false),
    field('weekly_lecture_sessions','Lecture sessions per week · blank means unconfirmed','number',false),
    field('weekly_tutorial_sessions','Tutorial sessions per week · blank means unconfirmed','number',false),
    field('weekly_practical_sessions','Practical sessions per week · blank means unconfirmed','number',false),
    field('lecture_session_minutes','Lecture session minutes','number',false),
    field('tutorial_session_minutes','Tutorial session minutes','number',false),
    field('practical_session_minutes','Practical session minutes','number',false),
  ]
  if (kind === 'section-teacher-assignments') return [
    field('requirement_id','Shared S5 subject requirement','select',true,getS5AssignmentOptions(data, academicYearId).requirements.map((r) => [String(r.id),String(data.subjects?.find((s) => String(s.id) === String(r.subject_id))?.subject_code ?? 'Subject') + ' · CSE S5'] as [string,string])),
    field('student_group_id','Protected section','select',true,getS5AssignmentOptions(data, academicYearId).groups.map((r) => [String(r.id),String(r.group_name) + ' · ' + String(r.student_count) + ' students'] as [string,string])),
    field('faculty_id','Teacher','select',true,(data.faculty ?? []).map((r) => [String(r.id),String(r.faculty_name) + ' (' + String(r.faculty_code) + ')'] as [string,string])),
  ]
  if (kind === 'activity-room-requirements') return [
    field('requirement_id','Shared subject requirement','select',true,getS5RequirementsForYear(data,academicYearId).map((r) => [String(r.id),String(data.subjects?.find((s)=>String(s.id)===String(r.subject_id))?.subject_code ?? 'Subject') + ' · CSE S5'] as [string,string])),
    field('activity_type','Activity type','select',true,[['lecture','Lecture'],['tutorial','Tutorial'],['practical','Practical']]),
    field('room_type','Required room type','select',true,[['classroom','Classroom'],['laboratory','Laboratory'],['other','Other']]),
  ]
  if (kind === 'activity-equipment-requirements') return [
    field('activity_requirement_id','Activity room requirement','select',true,(data['activity-room-requirements'] ?? []).filter((r)=>getS5RequirementsForYear(data,academicYearId).some((requirement)=>String(requirement.id)===String(r.requirement_id))).map((r) => [String(r.id),String(data.subjects?.find((s)=>String(s.id)===String(data['shared-subject-requirements']?.find((q)=>String(q.id)===String(r.requirement_id))?.subject_id))?.subject_code ?? 'Subject') + ' · ' + String(r.activity_type)] as [string,string])),
    field('capability_name','Required equipment or capability'),
  ]
  if (kind === 'faculty-scheduling-profiles') return [
    field('faculty_id','Faculty member','select',true,(data.faculty ?? []).map((r) => [String(r.id),String(r.faculty_name) + ' (' + String(r.faculty_code) + ')'] as [string,string])),
    field('max_daily_minutes','Maximum daily workload · minutes','number',false),
    field('max_weekly_minutes','Maximum weekly workload · minutes','number',false),
    field('is_confirmed','Availability and limits fully confirmed','checkbox',false),
  ]
  if (kind === 'faculty-availability-windows') return [
    field('profile_id','Faculty profile','select',true,(data['faculty-scheduling-profiles'] ?? []).map((r) => [String(r.id),String(data.faculty?.find((f)=>f.id===r.faculty_id)?.faculty_name ?? 'Faculty') + (r.is_confirmed ? ' · confirmed' : ' · incomplete')] as [string,string])),
    field('weekday','Weekday','select',true,weekdayOptions),
    field('availability','Window type','select',true,[['available','Available'],['unavailable','Unavailable']]),
    field('start_time','Start time','time'),
    field('end_time','End time','time'),
  ]
  if (kind === 'college-time-configurations') return [field('version','Configuration version','number'),field('academic_hour_minutes','Minutes per academic hour · required for generation','number',false),field('is_active','Active configuration','checkbox',false)]
  if (kind === 'college-working-days') return [
    field('configuration_id','Time configuration','select',true,(data['college-time-configurations'] ?? []).map((r) => [String(r.id),'Version ' + String(r.version) + (r.is_active ? ' · active' : '')] as [string,string])),
    field('weekday','Working day','select',true,weekdayOptions),
  ]
  if (kind === 'college-time-blocks') return [
    field('configuration_id','Time configuration','select',true,(data['college-time-configurations'] ?? []).map((r) => [String(r.id),'Version ' + String(r.version) + (r.is_active ? ' · active' : '')] as [string,string])),
    field('sequence_number','Display order','number'),
    field('block_type','Block type','select',true,[['teaching','Teaching period'],['break','Break'],['lunch','Lunch']]),
    field('period_number','Period number · teaching only','number',false),
    field('label','Optional label','text',false),
    field('start_time','Start time','time'),
    field('end_time','End time','time'),
    field('is_lab_compatible','Laboratory-compatible period','checkbox',false),
  ]
  if (kind === 'room-capabilities') return [
    field('room_id','Room','select',true,(data.rooms ?? []).map((r) => [String(r.id),String(r.room_name) + ' · ' + String(r.room_type)] as [string,string])),
    field('capability_name','Equipment or capability'),
    field('capability_type','Record type','select',true,[['equipment','Equipment'],['capability','Capability']]),
    field('quantity','Quantity · optional','number',false),
  ]
  if (kind === 'room-availability-profiles') return [
    field('room_id','Room','select',true,(data.rooms ?? []).map((r) => [String(r.id),String(r.room_name) + ' · ' + String(r.room_type)] as [string,string])),
    field('is_confirmed','Availability fully confirmed','checkbox',false),
  ]
  if (kind === 'room-availability-windows') return [
    field('profile_id','Room availability profile','select',true,(data['room-availability-profiles'] ?? []).map((r) => [String(r.id),String(data.rooms?.find((room) => room.id === r.room_id)?.room_name ?? 'Room') + (r.is_confirmed ? ' · confirmed' : ' · incomplete')] as [string,string])),
    field('weekday','Weekday','select',true,weekdayOptions),
    field('availability','Window type','select',true,[['available','Available'],['unavailable','Unavailable']]),
    field('start_time','Start time','time'),
    field('end_time','End time','time'),
  ]
  return null
}

function DataForm({ kind, collection, data, row, onSave, onCancel, error, busy, compact = false, academicYearId = '', disableSubmit = false }: { kind: string; collection: string; data: Data; row: Row | null; onSave: (event: FormEvent<HTMLFormElement>, kind: string, path: string, extra?: Record<string, unknown>) => void; onCancel?: () => void; error: string; busy: boolean; compact?: boolean; academicYearId?: string; disableSubmit?: boolean }) {
  const fields = extraInputFields(kind, data, academicYearId) ?? inputFields(kind, data)
  return <form className={`data-form ${compact ? 'compact-form' : ''}`} onSubmit={(event) => onSave(event, kind, `/${collection}${row ? `/${row.id}` : ''}`)} key={`${kind}-${row?.id ?? 'new'}`}>
    {fields.map(({name,label,type,required,options}) => <label className={`form-field ${type === 'checkbox' ? 'check-field' : ''}`} key={name}><span>{label}{required && <i> *</i>}</span>{type === 'select' ? <select name={name} defaultValue={String(row?.[name] ?? '')} required={required}><option value="" disabled>Select…</option>{options?.map(([value,caption]) => <option key={value} value={value}>{caption}</option>)}</select> : type === 'checkbox' ? <input name={name} type="checkbox" defaultChecked={defaultCheckboxValue(row, name)} /> : <input name={name} type={type} min={type === 'number' ? 0 : undefined} step={type === 'number' ? 1 : undefined} defaultValue={type === 'time' ? String(row?.[name] ?? '').slice(0,5) : String(row?.[name] ?? '')} required={required} />}</label>)}
    {error && <div className="form-error">{error}</div>}
    <div className="form-actions"><button className="primary-button" disabled={busy || disableSubmit}>{busy ? 'Saving…' : row ? 'Save changes' : <><Plus size={15} /> Add record</>}</button>{row && onCancel && <button type="button" className="secondary-button" onClick={onCancel}>Cancel</button>}</div>
  </form>
}

function ResourceSection({kind,title,description,rows,editing,setEditing,detail,setDetail,onSave,onDelete,formError,busy}: {kind:string;title:string;description:string;rows:Row[];editing:Row|null;setEditing:(row:Row|null)=>void;detail:Row|null;setDetail:(row:Row|null)=>void;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;onDelete:(collection:string,row:Row)=>void;formError:string;busy:boolean}) {
  const [localError,setLocalError] = useState('')
  const friendly = kind === 'rooms' ? 'Rooms' : 'Faculty'
  return <><PageIntro eyebrow="SOURCE DATA" title={title} description={description} action={<span className="count-badge">{rows.length} records</span>} />
    <div className="management-grid"><section className="panel list-panel"><div className="panel-heading"><div><h2>{friendly} directory</h2><p>All entries are saved in the academic data API.</p></div></div>{rows.length === 0 ? <EmptyState title={`No ${friendly.toLowerCase()} entered`} text="Use the form to add your first confirmed record." /> : <div className="record-list">{rows.map((row) => <RecordItem key={row.id} row={row} primary={String(row.faculty_name ?? row.room_name)} secondary={String(row.faculty_code ?? `${row.room_type} · capacity ${row.capacity}`)} onView={() => setDetail(row)} onEdit={() => {setEditing(row);setLocalError('')}} onDelete={() => onDelete(kind,row)} active={Boolean(row.is_active)} />)}</div>}
      {detail && <div className="detail-box"><button aria-label="Close detail" onClick={() => setDetail(null)}><X size={15}/></button><div className="section-eyebrow">RECORD DETAILS</div><h3>{String(detail.faculty_name ?? detail.room_name)}</h3><p>Record ID: {detail.id}</p>{Object.entries(detail).filter(([key]) => key !== 'id').map(([key,value]) => <div key={key}><span>{key.replaceAll('_',' ')}</span><strong>{value === null ? '—' : String(value)}</strong></div>)}</div>}
    </section><section className="panel form-panel"><div className="panel-heading"><div><div className="section-eyebrow">{editing ? 'EDIT RECORD' : 'MANUAL ENTRY'}</div><h2>{editing ? 'Update details' : `Add ${kind === 'rooms' ? 'a room' : 'a faculty member'}`}</h2><p>Required fields are marked with an asterisk.</p></div></div><DataForm kind={kind} collection={kind} data={{}} row={editing} onSave={(event,k,path)=>{void onSave(event,k,path)}} onCancel={() => setEditing(null)} error={localError || formError} busy={busy} />
    </section></div></>
}

function Structure({data,onSave,editing,setEditing,formError,busy}:{data:Data;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;editing:Row|null;setEditing:(row:Row|null)=>void;formError:string;busy:boolean}) {
  const [kind,setKind]=useState('academic-years')
  return <><PageIntro eyebrow="CSE DEPARTMENT" title="Academic structure" description="Set up departments, academic years, semesters, and class groups. No unconfirmed groups are added automatically." />
    <div className="structure-grid"><section className="panel"><div className="panel-heading"><div><div className="section-eyebrow">CURRENT CONFIGURATION</div><h2>Academic records</h2><p>Predefined groups are marked and protected from ordinary edits.</p></div></div>
      {(['departments','academic-years','semesters','student-groups'] as const).map((collection) => {const rows=data[collection] ?? [];return <div className="structure-block" key={collection}><h3>{collection.replaceAll('-',' ')}</h3>{rows.length===0?<p className="subtle-empty">Nothing entered yet.</p>:<div className="table-wrap"><table><thead><tr>{collection==='departments'?<><th>Name</th><th>Code</th></>:collection==='academic-years'?<><th>Name</th><th>Dates</th></>:collection==='semesters'?<><th>Semester</th><th>Year</th><th>Department</th></>:<><th>Group</th><th>Semester</th><th>Students</th><th>Type</th></>}<th>Action</th></tr></thead><tbody>{rows.map((row)=><tr key={row.id}>{collection==='departments'?<><td>{String(row.name)}</td><td>{String(row.code)}</td></>:collection==='academic-years'?<><td>{String(row.name)}</td><td>{String(row.start_date)} – {String(row.end_date)}</td></>:collection==='semesters'?<><td>{String(row.name)}</td><td>{String(data['academic-years']?.find(x=>x.id===row.academic_year_id)?.name ?? '—')}</td><td>{String(data.departments?.find(x=>x.id===row.department_id)?.name ?? '—')}</td></>:<><td>{String(row.group_name)}</td><td>{String(data.semesters?.find(x=>x.id===row.semester_id)?.name ?? '—')}</td><td>{String(row.student_count)}</td><td>{row.is_predefined?<span className="protected-badge">Predefined · protected</span>:<span className="record-status">Ordinary</span>}</td></>}<td>{collection==='student-groups'&&row.is_predefined?<span className="protected-badge">Protected</span>:<button className="assignment-edit" onClick={()=>{setKind(collection);setEditing(row)}}>Edit</button>}</td></tr>)}</tbody></table></div>}</div>})}
    </section><section className="panel form-panel"><div className="panel-heading"><div><div className="section-eyebrow">{editing?'EDIT RECORD':'MANUAL ENTRY'}</div><h2>{editing?'Update academic record':'Add academic record'}</h2><p>Choose a record type to see the right fields.</p></div></div><label className="form-field"><span>Record type</span><select value={kind} onChange={(e)=>{setKind(e.target.value);setEditing(null)}}><option value="departments">Department</option><option value="academic-years">Academic year</option><option value="semesters">Semester</option><option value="student-groups">Ordinary student group</option></select></label><div className="group-warning">Predefined groups keep their identity and student count fixed. Configure S5-A and S5-B from the S5 curriculum page or Excel group configuration template.</div><DataForm kind={kind} collection={kind} data={data} row={editing} onSave={(event,k,path)=>{void onSave(event,k,path)}} onCancel={()=>setEditing(null)} error={formError} busy={busy}/></section></div>
  </>
}

function Subjects({data,editing,setEditing,onSave,onDelete,formError,busy}:{data:Data;editing:Row|null;setEditing:(row:Row|null)=>void;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;onDelete:(collection:string,row:Row)=>void;formError:string;busy:boolean}) {
  const [assignmentKind,setAssignmentKind]=useState('semester-subjects')
  const subjects=data.subjects??[];const assignments=data['semester-subjects']??[];const facultyLinks=data['faculty-subjects']??[]
  const assignmentLabel=(item:Row)=>`${subjects.find(s=>s.id===item.subject_id)?.subject_code??'Subject'} · ${data['student-groups']?.find(g=>g.id===item.student_group_id)?.group_name??'Group'} · ${data.semesters?.find(s=>s.id===item.semester_id)?.name??'Semester'}`
  return <><PageIntro eyebrow="SOURCE DATA & CURRICULUM" title="Subject management" description="Maintain the subject catalogue, weekly group requirements, and faculty assignments." action={<span className="count-badge">{subjects.length} subjects</span>}/>
    <div className="management-grid"><section className="panel list-panel"><div className="panel-heading"><div><h2>Subject catalogue</h2><p>Subject definitions are separate from semester and group requirements.</p></div></div>{subjects.length===0?<EmptyState title="No subjects entered" text="Add confirmed subject names and codes to begin."/>:<div className="record-list">{subjects.map((row)=><RecordItem key={row.id} row={row} primary={`${row.subject_code} · ${row.subject_name}`} secondary={`${assignments.filter(a=>a.subject_id===row.id).length} group assignment(s)`} onView={()=>{setAssignmentKind('subjects');setEditing(row)}} onEdit={()=>{setAssignmentKind('subjects');setEditing(row)}} onDelete={()=>onDelete('subjects',row)} active={Boolean(row.is_active)}/>)}</div>}
      <div className="assignment-list"><div className="panel-heading"><div><h2>Group subject assignments</h2><p>Weekly requirements currently saved in the API.</p></div></div>{assignments.length===0?<p className="subtle-empty">No group subject assignments yet.</p>:assignments.map((a)=><div className="assignment-row" key={a.id}><BookOpen size={15}/><span><strong>{assignmentLabel(a)}</strong><small>{String(a.weekly_lecture_hours)} lecture · {String(a.weekly_tutorial_hours)} tutorial · {String(a.weekly_practical_hours)} practical hours/week</small></span><button className="assignment-edit" onClick={()=>{setAssignmentKind('semester-subjects');setEditing(a)}}>Edit</button><button className="icon-danger" aria-label="Delete assignment" onClick={()=>onDelete('semester-subjects',a)}><X size={15}/></button></div>)}</div>
      <div className="assignment-list"><div className="panel-heading"><div><h2>Faculty teaching assignments</h2><p>Links between faculty and group subject records.</p></div></div>{facultyLinks.length===0?<p className="subtle-empty">No faculty assignments yet.</p>:facultyLinks.map(link=><div className="assignment-row" key={link.id}><UsersRound size={15}/><span><strong>{String(data.faculty?.find(f=>f.id===link.faculty_id)?.faculty_name??'Faculty')} → {assignmentLabel(assignments.find(a=>a.id===link.semester_subject_id)??({} as Row))}</strong><small>Faculty assignment</small></span><button className="assignment-edit" onClick={()=>{setAssignmentKind('faculty-subjects');setEditing(link)}}>Edit</button><button className="icon-danger" aria-label="Delete faculty assignment" onClick={()=>onDelete('faculty-subjects',link)}><X size={15}/></button></div>)}</div>
    </section><section className="panel form-panel"><div className="panel-heading"><div><div className="section-eyebrow">MANUAL ENTRY</div><h2>{editing?'Edit record':'Add or assign'}</h2><p>Use the selector to manage catalogue entries and curriculum links.</p></div></div><label className="form-field"><span>Action</span><select value={assignmentKind} onChange={(e)=>{setAssignmentKind(e.target.value);setEditing(null)}}><option value="subjects">Add a subject</option><option value="semester-subjects">Assign subject to student group</option><option value="faculty-subjects">Assign faculty to group subject</option></select></label>{assignmentKind==='subjects'?<DataForm kind="subjects" collection="subjects" data={data} row={editing} onSave={(e,k,p)=>{void onSave(e,k,p)}} onCancel={()=>setEditing(null)} error={formError} busy={busy}/>:<DataForm kind={assignmentKind} collection={assignmentKind} data={data} row={editing} onSave={(e,k,p)=>{void onSave(e,k,p)}} onCancel={editing?()=>setEditing(null):undefined} error={formError} busy={busy}/>}</section></div></>
}

function S5Requirements({data,editing,setEditing,onSave,onDelete,formError,busy,refresh}:{data:Data;editing:Row|null;setEditing:(row:Row|null)=>void;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;onDelete:(collection:string,row:Row)=>void;formError:string;busy:boolean;refresh:()=>Promise<boolean>}) {
  const [selectedYear, setSelectedYear] = useState('')
  const [groupSetupBusy, setGroupSetupBusy] = useState(false)
  const [groupSetupError, setGroupSetupError] = useState('')
  const [groupSetupNotice, setGroupSetupNotice] = useState('')
  const readiness = buildS5Readiness(data, selectedYear)
  const { years, yearId, requirements, messages } = readiness
  const assignmentOptions = getS5AssignmentOptions(data, yearId)
  return <>
    <PageIntro eyebrow="CSE · SEMESTER 5" title="Shared S5 curriculum" description="Enter each subject requirement once for both sections. Teacher links remain separate for S5-A and S5-B." action={<span className="count-badge">{requirements.length} shared subject(s)</span>} />
    <section className="panel" style={{marginBottom:20}}><label className="form-field"><span>Academic year for S5 readiness and teacher assignments</span><select value={yearId} onChange={(event) => { setSelectedYear(event.target.value); setEditing(null) }}><option value="">No CSE S5 academic year configured</option>{years.map((year) => <option key={String(year.id)} value={String(year.id)}>{String(year.name)}{year.is_active ? ' · active' : ''}</option>)}</select></label></section>
    <div className="group-protection-note"><ShieldCheck size={17}/><p><strong>Predefined sections:</strong> S5-A and S5-B each have 72 students. Their identity and count remain protected. Configure them once for the selected year before assigning teachers.</p></div>
    <section className="panel" style={{marginBottom:20}}><div className="panel-heading"><div><div className="section-eyebrow">FIXED SECTION SETUP</div><h2>Configure S5-A and S5-B</h2><p>This creates or verifies the two protected groups for the selected CSE S5 academic year. It never changes an existing group.</p></div><button className="primary-button" disabled={!yearId||groupSetupBusy||assignmentOptions.ambiguous} onClick={()=>void (async()=>{setGroupSetupBusy(true);setGroupSetupError('');setGroupSetupNotice('');try{const year=years.find((item)=>String(item.id)===yearId);if(!year)throw new Error('Select an academic year that has a CSE S5 semester.');await api('/predefined-groups/configure-s5',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({academic_year_name:year.name})});setGroupSetupNotice('Protected S5-A and S5-B groups are saved for this year.');await refresh()}catch(cause){setGroupSetupError(cause instanceof Error?cause.message:'Could not configure the protected groups.')}finally{setGroupSetupBusy(false)}})()}>{groupSetupBusy?'Saving…':'Create or verify groups'}</button></div>{groupSetupError&&<p className="form-error" role="alert">{groupSetupError}</p>}{groupSetupNotice&&<div className="alert success-alert" role="status">{groupSetupNotice}</div>}</section>
    <section className="panel" style={{marginBottom:20}}><div className="panel-heading"><div><div className="section-eyebrow">DATA READINESS</div><h2>Missing or unconfirmed information</h2><p>These checks describe saved records; no timetable data is generated.</p></div></div>
      <ul className="readiness-list" style={{margin:'8px 0 0',paddingLeft:20,color:'#72768a',fontSize:13,lineHeight:1.8}}>
        {messages.length ? messages.map((message, index) => <li key={`${index}-${message}`}>{message}</li>) : <li>S5 groups and entered requirement data are ready for review.</li>}
      </ul>
    </section>
    {assignmentOptions.ambiguous && <div className="alert error-alert" role="status">More than one CSE S5 semester exists for this academic year. Resolve the academic structure before creating teacher assignments.</div>}
    {!assignmentOptions.ambiguous && assignmentOptions.requirements.length === 0 && <div className="alert error-alert" role="status">No eligible shared CSE S5 subject requirements are available for the selected academic year. Add a shared requirement for that year before assigning teachers.</div>}
    {!assignmentOptions.ambiguous && assignmentOptions.groups.length === 0 && <div className="alert error-alert" role="status">No eligible protected S5-A or S5-B groups are available for the selected academic year. Configure the protected groups for that year before assigning teachers.</div>}
    <DataManager title="Shared subject requirements and section teachers" description="Create one S5 requirement per subject, then add teacher links separately for each protected section." kinds={s5DataKinds} data={data} editing={editing} setEditing={setEditing} onSave={onSave} onDelete={onDelete} formError={formError} busy={busy} academicYearId={yearId} />
  </>
}

const s5DataKinds: [string,string][] = [['shared-subject-requirements','Shared subject requirement'],['section-teacher-assignments','Section teacher assignment'],['activity-room-requirements','Activity room requirement'],['activity-equipment-requirements','Activity equipment requirement']]
const facultyDataKinds: [string,string][] = [['faculty-scheduling-profiles','Availability and workload profile'],['faculty-availability-windows','Faculty availability window']]

function ConfigurationPage({data,editing,setEditing,onSave,onDelete,formError,busy}:{data:Data;editing:Row|null;setEditing:(row:Row|null)=>void;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;onDelete:(collection:string,row:Row)=>void;formError:string;busy:boolean}) {
  const active = (data['college-time-configurations'] ?? []).find((config) => config.is_active)
  const activeDays = (data['college-working-days'] ?? []).filter((row) => row.configuration_id === active?.id)
  const activeBlocks = (data['college-time-blocks'] ?? []).filter((row) => row.configuration_id === active?.id)
  return <>
    <PageIntro eyebrow="COLLEGE-WIDE RULES" title="Timetable configuration" description="Enter the confirmed working days, periods and breaks. No official college times are prefilled." action={<span className="format-pill">No Period Z</span>} />
    <div className="shared-time-note" style={{marginBottom:20}}><CalendarDays size={16}/><span><strong>{active ? 'Active configuration · version ' + String(active.version) : 'No active college time configuration'}</strong><small>Period times and lunch must come from confirmed college information. The earlier S5-B timetable is only a provisional reference.</small></span></div>
    <section className="panel" style={{marginBottom:20}}><div className="panel-heading"><div><div className="section-eyebrow">DATA READINESS</div><h2>Configuration completeness</h2></div></div><ul style={{margin:'8px 0 0',paddingLeft:20,color:'#72768a',fontSize:13,lineHeight:1.8}}>
      {!active && <li>No active college time configuration is saved.</li>}
      {active && activeDays.length === 0 && <li>No working days are configured for the active version.</li>}
      {active && activeBlocks.filter((block) => block.block_type === 'teaching').length === 0 && <li>No teaching periods are configured for the active version.</li>}
      {active && activeBlocks.filter((block) => block.block_type === 'lunch').length === 0 && <li>No lunch interval is configured for the active version.</li>}
      {active && activeBlocks.some((block) => block.block_type === 'teaching') && !hasLabCompatiblePeriod(activeBlocks) && <li>No teaching period is marked laboratory-compatible. Confirm at least one lab period if practical sessions need scheduling.</li>}
    </ul></section>
    <DataManager title="College time settings" description="Create a configuration, then enter its working weekdays and ordered teaching/break intervals." kinds={configurationKinds} data={data} editing={editing} setEditing={setEditing} onSave={onSave} onDelete={onDelete} formError={formError} busy={busy} />
  </>
}

function RoomReadiness({data}:{data:Data}) {
  const rooms=data.rooms??[]
  const labs=rooms.filter((room)=>room.room_type==='laboratory')
  const classrooms=rooms.filter((room)=>room.room_type==='classroom')
  const profiles=data['room-availability-profiles']??[]
  const capabilities=data['room-capabilities']??[]
  return <section className="panel" style={{marginBottom:20}}><div className="panel-heading"><div><div className="section-eyebrow">ROOM DATA READINESS</div><h2>Rooms, equipment and availability</h2></div></div><ul style={{margin:'8px 0 0',paddingLeft:20,color:'#72768a',fontSize:13,lineHeight:1.8}}>
    {classrooms.length===0&&<li>No classroom details have been entered.</li>}
    {classrooms.filter((room)=>Number(room.capacity)<75).map((room)=><li key={'capacity-'+room.id}>{String(room.room_name)} has capacity {String(room.capacity)}; it is below the confirmed classroom capacity of 75.</li>)}
    {labs.length<4&&<li>{labs.length} of 4 shared laboratory records are entered. Add the actual identifiers and details when confirmed.</li>}
    {rooms.filter((room)=>!profiles.some((profile)=>profile.room_id===room.id)).map((room)=><li key={'profile-'+room.id}>{String(room.room_name)} has no availability profile yet.</li>)}
    {profiles.filter((profile)=>!profile.is_confirmed).map((profile)=><li key={'confirmed-'+profile.id}>{String(rooms.find((room)=>room.id===profile.room_id)?.room_name??'A room')} availability is not confirmed.</li>)}
    {rooms.length>0&&capabilities.length===0&&<li>No room equipment or capabilities have been entered.</li>}
  </ul></section>
}

const configurationKinds: [string,string][] = [['college-time-configurations','Configuration'],['college-working-days','Working day'],['college-time-blocks','Period, break or lunch']]

function DataManager({title,description,kinds,data,editing,setEditing,onSave,onDelete,formError,busy,academicYearId=''}:{title:string;description:string;kinds:[string,string][];data:Data;editing:Row|null;setEditing:(row:Row|null)=>void;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;onDelete:(collection:string,row:Row)=>void;formError:string;busy:boolean;academicYearId?:string}) {
  const [kind,setKind]=useState(kinds[0][0])
  const [editingKind,setEditingKind]=useState('')
  const assignmentOptions=kind==='section-teacher-assignments'?getS5AssignmentOptions(data,academicYearId):null
  const selectedRequirementIds=new Set(getS5RequirementsForYear(data,academicYearId).map((row)=>String(row.id)))
  const selectedActivityIds=new Set((data['activity-room-requirements']??[]).filter((row)=>selectedRequirementIds.has(String(row.requirement_id))).map((row)=>String(row.id)))
  const rows=kind==='section-teacher-assignments'&&assignmentOptions
    ? (data[kind]??[]).filter((row)=>assignmentOptions.requirements.some((requirement)=>String(requirement.id)===String(row.requirement_id))&&assignmentOptions.groups.some((group)=>String(group.id)===String(row.student_group_id)))
    : kind==='activity-room-requirements' ? (data[kind]??[]).filter((row)=>selectedRequirementIds.has(String(row.requirement_id)))
    : kind==='activity-equipment-requirements' ? (data[kind]??[]).filter((row)=>selectedActivityIds.has(String(row.activity_requirement_id)))
    : data[kind] ?? []
  const formRow=editingKind===kind ? editing : null
  const assignmentBlocked=Boolean(assignmentOptions && (!assignmentOptions.requirements.length || !assignmentOptions.groups.length))
  function summary(row:Row):[string,string] {
    const subject=(id:unknown)=>String(data.subjects?.find((item)=>item.id===id)?.subject_code ?? 'Subject')
    const group=(id:unknown)=>String(data['student-groups']?.find((item)=>item.id===id)?.group_name ?? 'Section')
    const teacher=(id:unknown)=>String(data.faculty?.find((item)=>item.id===id)?.faculty_name ?? 'Teacher')
    const room=(id:unknown)=>String(data.rooms?.find((item)=>item.id===id)?.room_name ?? 'Room')
    if(kind==='shared-subject-requirements') return [subject(row.subject_id),'Hours L/T/P: ' + [row.weekly_lecture_hours,row.weekly_tutorial_hours,row.weekly_practical_hours].map((value)=>String(value ?? 'unconfirmed')).join('/') + ' · sessions/week L/T/P: ' + [row.weekly_lecture_sessions,row.weekly_tutorial_sessions,row.weekly_practical_sessions].map((value)=>String(value ?? 'unconfirmed')).join('/') + ' · minutes/session L/T/P: ' + [row.lecture_session_minutes,row.tutorial_session_minutes,row.practical_session_minutes].map((value)=>String(value ?? 'unconfirmed')).join('/')]
    if(kind==='section-teacher-assignments') return [teacher(row.faculty_id)+' → '+group(row.student_group_id),subject(data['shared-subject-requirements']?.find((item)=>item.id===row.requirement_id)?.subject_id)+' · section-specific assignment']
    if(kind==='activity-room-requirements') return [subject(data['shared-subject-requirements']?.find((item)=>item.id===row.requirement_id)?.subject_id)+' · '+String(row.activity_type),String(row.room_type)+' required']
    if(kind==='activity-equipment-requirements') return [String(data['activity-room-requirements']?.find((item)=>item.id===row.activity_requirement_id)?.activity_type ?? 'Activity'),String(row.capability_name)+' required']
    if(kind==='faculty-scheduling-profiles') return [String(data.faculty?.find((item)=>item.id===row.faculty_id)?.faculty_name ?? 'Faculty'),row.is_confirmed?'Availability and workload confirmed':'Availability or workload incomplete']
    if(kind==='faculty-availability-windows') return [String(data.faculty?.find((member)=>member.id===data['faculty-scheduling-profiles']?.find((profile)=>profile.id===row.profile_id)?.faculty_id)?.faculty_name ?? 'Faculty'),String(weekdays.find(([value])=>value===String(row.weekday))?.[1] ?? row.weekday)+' · '+String(row.start_time)+'–'+String(row.end_time)+' · '+String(row.availability)]
    if(kind==='college-time-configurations') return ['Configuration version '+String(row.version),row.is_active?'Active':'Inactive']
    if(kind==='college-working-days') return ['Working day',weekdays.find(([value])=>value===String(row.weekday))?.[1] ?? String(row.weekday)]
    if(kind==='college-time-blocks') return [row.block_type==='teaching'?'Period '+String(row.period_number):String(row.label ?? row.block_type),String(row.start_time)+'–'+String(row.end_time)+(row.is_lab_compatible?' · lab-compatible':'')]
    if(kind==='room-capabilities') return [room(row.room_id),String(row.capability_name)+' · '+String(row.capability_type)+(row.quantity?' · qty '+String(row.quantity):'')]
    if(kind==='room-availability-profiles') return [room(row.room_id),row.is_confirmed?'Availability confirmed':'Availability incomplete']
    return [room(data['room-availability-profiles']?.find((item)=>item.id===row.profile_id)?.room_id),String(weekdays.find(([value])=>value===String(row.weekday))?.[1] ?? row.weekday)+' · '+String(row.start_time)+'–'+String(row.end_time)+' · '+String(row.availability)]
  }
  return <div className="management-grid"><section className="panel list-panel"><div className="panel-heading"><div><h2>{title}</h2><p>{description}</p></div></div><label className="form-field"><span>Show</span><select value={kind} onChange={(event)=>{setKind(event.target.value);setEditing(null);setEditingKind('')}}>{kinds.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>{rows.length===0?<EmptyState title={'No '+kinds.find(([value])=>value===kind)?.[1].toLowerCase()+' records'} text="Enter only confirmed information. No sample records are created."/>:<div className="record-list">{rows.map((row)=>{const [primary,secondary]=summary(row);const active=Boolean(row.is_active ?? row.is_confirmed ?? true);return <RecordItem key={row.id} row={row} primary={primary} secondary={secondary} active={active} onView={()=>{setEditing(row);setEditingKind(kind)}} onEdit={()=>{setEditing(row);setEditingKind(kind)}} onDelete={()=>onDelete(kind,row)}/>})}</div>}</section><section className="panel form-panel"><div className="panel-heading"><div><div className="section-eyebrow">{formRow?'EDIT RECORD':'MANUAL ENTRY'}</div><h2>{formRow?'Update details':'Add '+kinds.find(([value])=>value===kind)?.[1].toLowerCase()}</h2><p>Required values are checked by the API before saving.</p></div></div>{assignmentBlocked&&<p className="form-error" role="status">Choose an academic year with both a shared CSE S5 requirement and a protected S5-A or S5-B group to enable assignments.</p>}<DataForm kind={kind} collection={kind} data={data} row={formRow} academicYearId={academicYearId} disableSubmit={assignmentBlocked} onSave={(event,k,path)=>{void onSave(event,k,path)}} onCancel={()=>{setEditing(null);setEditingKind('')}} error={formError} busy={busy}/></section></div>
}

function Groups({data,onSave,editing,setEditing,onDelete,formError,busy}:{data:Data;onSave:(event:FormEvent<HTMLFormElement>,kind:string,path:string,extra?:Record<string,unknown>)=>void;editing:Row|null;setEditing:(row:Row|null)=>void;onDelete:(collection:string,row:Row)=>void;formError:string;busy:boolean}) {
  const groups=data['student-groups']??[]
  return <><PageIntro eyebrow="FIXED ACADEMIC CONFIGURATION" title="Student groups" description="Predefined group identity, semester, and student count are protected from ordinary editing." action={<span className="count-badge">{groups.length} groups</span>}/><div className="group-protection-note"><ShieldCheck size={17}/><p><strong>Protected groups are read-only here.</strong> Their names, semester links, and student counts can only be set through explicit predefined-group configuration. No groups are assumed or added automatically.</p></div><div className="management-grid"><section className="panel list-panel"><div className="panel-heading"><div><h2>Configured student groups</h2><p>Semester and student counts come from saved academic records.</p></div></div>{groups.length===0?<EmptyState title="No student groups configured" text="Add an ordinary group manually, or use the protected configuration route for predefined groups."/>:<div className="record-list">{groups.map(row=>{const semester=data.semesters?.find(s=>s.id===row.semester_id);const year=data['academic-years']?.find(y=>y.id===semester?.academic_year_id);return <div className="record-item" key={row.id}><div className="record-avatar group-avatar"><UsersRound size={17}/></div><div className="record-copy"><strong>{String(row.group_name)}</strong><small>{String(semester?.name??'Semester not found')} · {String(year?.name??'Academic year')}</small></div><div className="group-count"><strong>{String(row.student_count)}</strong><small>students</small></div>{row.is_predefined?<span className="protected-badge">Protected</span>:<div className="record-actions"><button onClick={()=>setEditing(row)}>Edit</button><button className="danger-text" onClick={()=>onDelete('student-groups',row)}>Delete</button></div>}</div>})}</div>}</section><section className="panel form-panel"><div className="panel-heading"><div><div className="section-eyebrow">ORDINARY GROUP</div><h2>{editing?'Edit ordinary group':'Add ordinary group'}</h2><p>Predefined groups cannot be created or edited through this form.</p></div></div><DataForm kind="student-groups" collection="student-groups" data={data} row={editing} onSave={(e,k,p)=>{void onSave(e,k,p)}} onCancel={()=>setEditing(null)} error={formError} busy={busy}/></section></div></>
}

function ImportSection({onImported}:{onImported:()=>Promise<boolean>}) {
  const [kind,setKind]=useState('faculty');const [file,setFile]=useState<File|null>(null);const [preview,setPreview]=useState<{preview_id:string;row_count:number;valid_count:number;errors:{row:number;column:string;message:string}[];rows:Record<string,unknown>[];can_apply:boolean}|null>(null);const [error,setError]=useState('');const [message,setMessage]=useState('');const [busy,setBusy]=useState(false)
  const templates=[['faculty','Faculty'],['rooms','Rooms & laboratories'],['subjects','Subjects'],['semester-subjects','Subject & group assignments'],['student-groups','Protected group configuration']]
  const choose=(next:string)=>{setKind(next);setPreview(null);setFile(null);setError('');setMessage('')}
  const makeForm=(apply=false)=>{const form=new FormData();if(file)form.append('file',file);if(apply&&preview)form.append('expected_preview_id',preview.preview_id);return form}
  async function doPreview(){if(!file){setError('Choose an .xlsx file first.');return}if(!file.name.toLowerCase().endsWith('.xlsx')){setError('Only Excel .xlsx files are supported.');return}if(file.size>5*1024*1024){setError('The file is larger than 5 MB.');return}setBusy(true);setError('');setMessage('');try{const result=await api<typeof preview>(`/${'imports'}/${kind}/preview`,{method:'POST',body:makeForm()});setPreview(result)}catch(e){setError(e instanceof Error?e.message:'Could not preview this workbook.')}finally{setBusy(false)}}
  async function doApply(){if(!file||!preview?.can_apply)return;if(!window.confirm(`Import all ${preview.valid_count} rows? Nothing will be overwritten.`))return;setBusy(true);setError('');try{const result=await api<{imported_count:number;message:string}>(`/imports/${kind}/apply`,{method:'POST',body:makeForm(true)});setMessage(`${result.message} ${result.imported_count} row(s) saved to the database.`);setPreview(null);setFile(null);if(!await onImported())setMessage(`${result.imported_count} row(s) were saved to the database, but the latest records could not be reloaded. Retry loading before continuing.`)}catch(e){setError(e instanceof Error?e.message:'Import could not be applied.')}finally{setBusy(false)}}
  return <><PageIntro eyebrow="BULK DATA ENTRY" title="Excel import" description="Download a template, fill it with confirmed data, inspect the preview, then explicitly apply it." action={<span className="format-pill">.xlsx · up to 5 MB</span>}/><div className="import-grid"><section className="panel template-panel"><div className="panel-heading"><div><div className="section-eyebrow">STEP 1 · DOWNLOAD A TEMPLATE</div><h2>Choose the data type</h2><p>Templates use the exact column names expected by the backend.</p></div></div><label className="form-field"><span>Template type</span><select value={kind} onChange={e=>choose(e.target.value)}>{templates.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><a className="download-template" href={`${API_BASE}/imports/templates/${kind}`}><Download size={17}/><span><strong>Download {templates.find(t=>t[0]===kind)?.[1]} template</strong><small>Excel workbook · .xlsx</small></span><ChevronRight size={16}/></a><div className="template-help"><strong>Before importing</strong><ul><li>Keep the template column names unchanged.</li><li>Imports add new records only. Existing records are never overwritten.</li><li>Semester subject templates reference existing records by numeric IDs.</li><li>Protected group imports use the explicit group configuration rules.</li></ul></div></section>
      <section className="panel import-panel"><div className="panel-heading"><div><div className="section-eyebrow">STEP 2 · PREVIEW AND CONFIRM</div><h2>Upload your completed file</h2><p>The backend validates the workbook before saving any rows.</p></div></div><label className="upload-box"><Upload size={22}/><strong>{file?.name??'Select an .xlsx workbook'}</strong><span>{file?`${(file.size/1024).toFixed(1)} KB · click to choose another`:'Maximum file size: 5 MB'}</span><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={e=>{setFile(e.target.files?.[0]??null);setPreview(null);setError('')}}/></label><button className="primary-button wide-button" disabled={busy||!file} onClick={()=>void doPreview()}>{busy&&!preview?<><LoaderCircle size={16} className="spin"/> Checking workbook…</>:<>Preview import <ChevronRight size={15}/></>}</button>
        {error&&<div className="form-error">{error}</div>}{message&&<div className="import-success"><Check size={16}/>{message}</div>}
        {preview&&<div className="preview-area"><div className="preview-summary"><strong>Import preview</strong><span>{preview.valid_count} valid of {preview.row_count} rows</span></div>{preview.rows.length>0&&<div className="preview-table"><table><thead><tr>{Object.keys(preview.rows[0]).map(k=><th key={k}>{k.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{preview.rows.slice(0,10).map((row,i)=><tr key={i}>{Object.values(row).map((v,j)=><td key={j}>{String(v??'—')}</td>)}</tr>)}</tbody></table></div>}{preview.errors.length>0&&<div className="import-errors"><strong>{preview.errors.length} issue(s) to fix</strong>{preview.errors.map((e,i)=><p key={i}>Row {e.row}, {e.column}: {e.message}</p>)}</div>}{preview.row_count>10&&<small>Showing up to 10 rows in this preview.</small>}<button className="primary-button wide-button" disabled={busy||!preview.can_apply} onClick={()=>void doApply()}>{busy&&preview.can_apply?'Applying…':<>Confirm and import {preview.valid_count} row(s) <Check size={15}/></>}</button></div>}
      </section></div><p className="security-note"><ShieldCheck size={15}/> Server-side validation is required for every import. This local prototype has no administrator login; do not expose it publicly.</p></>
}

function RecordItem({primary,secondary,onView,onEdit,onDelete,active}: {row:Row;primary:string;secondary:string;onView:()=>void;onEdit:()=>void;onDelete:()=>void;active:boolean}) {
  return <div className="record-item"><div className="record-avatar">{primary.slice(0,1).toUpperCase()}</div><button className="record-copy text-button" onClick={onView}><strong>{primary}</strong><small>{secondary}</small></button><span className={`record-status ${active?'active-status':''}`}>{active?'Active':'Inactive'}</span><div className="record-actions"><button onClick={onEdit}>Edit</button><button className="danger-text" onClick={onDelete}>Delete</button></div></div>
}
function EmptyState({title,text}:{title:string;text:string}) {return <div className="empty-state"><span className="empty-icon"><BookOpen size={20}/></span><strong>{title}</strong><p>{text}</p></div>}

export default App
