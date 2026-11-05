#!/usr/bin/env python3
"""Complete, measure, save and publish the existing RocketNozzle-LLM project."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from container_jobs import Jobs, OWNER, OWNER_KEY, RUN_KEY, run_id  # noqa: E402
from github_publish import checked_origin  # noqa: E402
from host_common import ROOT, ProjectError, Runner, folder, safe, write_json  # noqa: E402

PREFIX = "docs/final/"


def sha(path):
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):
            value.update(block)
    return value.hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def available_ram():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1])*1024
    return 0


class Workflow:
    def __init__(self,args):
        self.args=args
        self.runner=Runner()
        self.jobs=None
        self.keepalive=None
        self.stop_keepalive=threading.Event()
        self.published=True

    def publish(self):
        if self.args.local_only:
            self.published=False
            return False
        try:
            if not checked_origin(self.runner):
                raise ProjectError('Expected GitHub origin is missing; no remote was added')
            branch=self.runner.git('branch','--show-current')
            if not branch:
                raise ProjectError('Detached HEAD cannot be published')
            # Standard credential helpers and SSH configuration remain on the host.
            # No login, visibility change, force push, merge or reset occurs here.
            prefix=['git','-c','core.sshCommand=ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes']
            env=dict(os.environ,GIT_TERMINAL_PROMPT='0')
            transport=subprocess.run(prefix+['ls-remote','origin','refs/heads/'+branch],cwd=ROOT,
                                     capture_output=True,text=True,env=env,timeout=90)
            if transport.returncode:
                raise ProjectError('Git transport authentication or connectivity failed')
            remote=transport.stdout.strip().split()
            if remote:
                fetch=subprocess.run(prefix+['fetch','--no-tags','origin',branch],cwd=ROOT,
                                     capture_output=True,text=True,env=env,timeout=180)
                if fetch.returncode or self.runner.run(['git','merge-base','--is-ancestor','FETCH_HEAD','HEAD'],
                                                       check=False,logged=False)[0]:
                    raise ProjectError('Remote branch has changes not in local HEAD; history was preserved')
            tags=self.runner.git('tag','--list','v0.4.0*').splitlines()+self.runner.git('tag','--list','v0.5.0*').splitlines()+self.runner.git('tag','--list','v1.0.0*').splitlines()
            result=subprocess.run(prefix+['push','--atomic','--set-upstream','origin','HEAD:refs/heads/'+branch,
                                          *['refs/tags/'+t+':refs/tags/'+t for t in tags]],
                                  cwd=ROOT,text=True,capture_output=True,env=env,timeout=300)
            if result.returncode:
                # GitHub errors contain only the previously validated non-secret origin.
                print('PUSH_PENDING:',result.stderr.strip()[-1200:],flush=True)
                raise ProjectError('Push was rejected or interrupted; local commits remain saved')
            verify=subprocess.run(prefix+['ls-remote','origin','refs/heads/'+branch],cwd=ROOT,
                                  capture_output=True,text=True,env=env,timeout=90)
            local=self.runner.git('rev-parse','HEAD')
            if verify.returncode or not verify.stdout.startswith(local+'\t'):
                raise ProjectError('Remote HEAD readback did not match local HEAD')
            write_json('logs/setup/final-publication.json',dict(status='published',head=local,branch=branch,
                                                              checked_utc=utc(),tags=tags))
            self.published=True
            print('CHECKPOINT_PUSHED:',local[:12],flush=True)
            return True
        except (ProjectError,subprocess.SubprocessError) as error:
            self.published=False
            write_json('logs/setup/final-publication.json',dict(status='pending',reason=str(error),checked_utc=utc()))
            print('PUBLICATION_PENDING:',str(error),'Local work continues.',flush=True)
            return False

    def checkpoint(self,paths,message,tag=None):
        paths=sorted(set(str(p) for p in paths))
        if self.runner.git('diff','--cached','--name-only'):
            raise ProjectError('An unexpected staged change was preserved')
        changed=self.runner.git('status','--porcelain','--untracked-files=all','--',*paths)
        if changed:
            self.runner.run(['git','add','--',*paths])
            self.runner.run(['git','commit','-m',message])
        if self.runner.git('status','--porcelain','--untracked-files=all'):
            raise ProjectError('Unexpected edits remain after the scoped checkpoint; preserved')
        chosen=None
        if tag:
            code,_=self.runner.run(['git','rev-parse','--verify','--quiet','refs/tags/'+tag],check=False,logged=False)
            if code:
                chosen=tag
            elif self.runner.git('rev-parse',tag+'^{commit}')==self.runner.git('rev-parse','HEAD'):
                chosen=tag
            else:
                chosen=tag+'-run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
            code,_=self.runner.run(['git','rev-parse','--verify','--quiet','refs/tags/'+chosen],check=False,logged=False)
            if code:
                self.runner.run(['git','tag','-a',chosen,'-m',message])
        self.publish()
        return chosen

    def preflight(self):
        if os.geteuid()==0:
            raise ProjectError('Run as heavenly, without sudo before the launcher')
        if platform.system()!='Linux' or platform.machine() not in {'x86_64','amd64'}:
            raise ProjectError('This frozen CPU workflow requires Linux x86_64')
        if sys.version_info<(3,11):
            raise ProjectError('Host Python 3.11+ is required')
        if self.runner.git('rev-parse','--show-toplevel')!=str(ROOT):
            raise ProjectError('Repository root differs from the selected project')
        if not checked_origin(self.runner):
            raise ProjectError('Expected origin is missing')
        for name in ('user.name','user.email'):
            if not self.runner.git('config','--get',name,check=False).strip():
                raise ProjectError('Set your real Git '+name+' locally before running')
        for marker in ('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD'):
            location=self.runner.git('rev-parse','--git-path',marker)
            if (ROOT/location).exists():
                raise ProjectError('An unfinished Git operation was preserved')
        install_record=safe('tmp/final-install-intent.json')
        owned=set(json.loads(install_record.read_text())['files']) if install_record.exists() else set()
        status=self.runner.git('status','--porcelain','--untracked-files=all')
        for line in status.splitlines():
            if line[3:] not in owned:
                raise ProjectError('Unrelated local edit preserved: '+line[3:])
        if status and not owned:
            raise ProjectError('Save unrelated Git edits before starting')
        for path in owned:
            expected=json.loads(install_record.read_text())['files'][path]['sha256']
            if not safe(path).is_file() or sha(safe(path))!=expected:
                raise ProjectError('Installed source changed before its checkpoint: '+path)
        if self.runner.git('diff','--cached','--name-only'):
            raise ProjectError('Pre-existing staged changes were preserved')
        if shutil.disk_usage(ROOT).free < 6*1024**3:
            raise ProjectError('Need at least 6 GiB of free project disk space')
        if available_ram()<6*1024**3:
            raise ProjectError('Need at least 6 GiB currently available RAM; close large applications and rerun')
        selected=json.loads(safe('configs/stack-selection.json').read_text())
        if selected['model']['original_model']!='Qwen/Qwen3.5-4B':
            raise ProjectError('The frozen experiment expects the existing Qwen3.5-4B selection')
        lock=json.loads(safe('configs/environment-lock.json').read_text())
        if sha(safe('uv.lock'))!=lock['uv_lock_sha256']:
            raise ProjectError('Existing dependency lock hash differs; preserved')
        self.checkpoint(owned,'feat: freeze complete nozzle benchmark evaluator and automated hand-in workflow')
        write_json('logs/setup/final-preflight.json',dict(status='passed',utc=utc(),available_ram=available_ram(),
            free_disk=shutil.disk_usage(ROOT).free,host_python=platform.python_version(),platform=platform.platform()))

    def sudo(self):
        if not shutil.which('sudo'):
            raise ProjectError('sudo is missing on this host')
        self.runner.run(['sudo','-v'],interactive=True)
        if self.keepalive:
            return
        def maintain():
            while not self.stop_keepalive.wait(45):
                subprocess.run(['sudo','-n','-v'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.keepalive=threading.Thread(target=maintain,daemon=True)
        self.keepalive.start()

    def connect_docker(self):
        if not shutil.which('docker'):
            raise ProjectError('The Stage 03 Docker installation is missing; this launcher does not replace system Docker')
        socket=['--host','unix:///var/run/docker.sock']
        code,_=self.runner.run(['docker',*socket,'info'],check=False,logged=False)
        if code:
            self.sudo()
            docker=['sudo','-n','docker',*socket]
            code,_=self.runner.run(docker+['info'],check=False,logged=False)
            if code:
                self.runner.run(['sudo','-n','systemctl','start','docker'])
        else:
            docker=['docker',*socket]
        self.jobs=Jobs(self.runner,docker)
        _,info=self.jobs.call('info','--format','{{json .}}',logged=False)
        info=json.loads(info)
        if str(info.get('CgroupVersion'))!='2':
            raise ProjectError('cgroup v2 is required for the bounded jobs')
        self.jobs.call('compose','version',logged=False)
        # The shared old/new command lock makes interrupted-resource recovery safe.
        self.jobs.cleanup()

    def rendering_tools(self):
        missing=not all(shutil.which(x) for x in ('libreoffice','pdftoppm','pdftotext','pdfinfo'))
        if missing:
            if not shutil.which('apt-get'):
                raise ProjectError('Need LibreOffice Impress and Poppler on this Linux host')
            self.sudo()
            self.runner.run(['sudo','-n','apt-get','update'],timeout=600)
            self.runner.run(['sudo','-n','env','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y',
                '--no-remove','--no-install-recommends','libreoffice-impress','poppler-utils','fonts-liberation'],timeout=1800)
        _,version=self.runner.run(['libreoffice','--version'],logged=False)
        write_json('logs/setup/presentation-runtime.json',dict(libreoffice=version.strip(),utc=utc()))

    def images(self):
        from environment import ensure_images, worker_specification, verify_worker
        locked=json.loads(safe('configs/environment-lock.json').read_text())
        receipt=json.loads(safe('configs/build-receipt.json').read_text())
        images=receipt['images']
        if any(self.jobs.inspect(value['id'],kind='image') is None for value in images.values()):
            print('Rebuilding missing images from the saved pins; existing pins will not be refreshed.',flush=True)
            images=ensure_images(self.jobs,locked)
            self.publish()
        for name,image in images.items():
            item=self.jobs.inspect(image['id'],kind='image')
            if item is None or item.get('Architecture')!='amd64':
                raise ProjectError('Pinned '+name+' image is unavailable or has the wrong architecture')
        verify_worker(self.jobs,images['worker'],worker_specification(locked))
        model=json.loads(safe('configs/stack-selection.json').read_text())['model']
        weights=folder('models')/model['filename']
        if not weights.is_file():
            self.jobs.job(images['worker']['id'],['download-model'],kind='final-model-download',network='bridge',
                          timeout=10800,extra_mounts=[(weights.parent,'/models',False)])
        if weights.is_symlink() or weights.stat().st_size!=model['size_bytes'] or sha(weights)!=model['sha256']:
            raise ProjectError('Model checksum/byte count differs; model file preserved')
        code=self.jobs.job(images['llama']['id'],['--help'],kind='final-server-check',timeout=120)
        help_text=(ROOT/code['log_path']/'container.log').read_text()
        if any(flag not in help_text for flag in ('--jinja','--chat-template-kwargs','--ctx-size')):
            raise ProjectError('Saved llama-server lacks the required chat-template API settings')
        write_json('logs/setup/final-runtime.json',dict(images=images,model=model,uv_lock=locked['uv_lock_sha256']))
        return images

    def code_mounts(self):
        return [(safe(name),'/app/'+name,True) for name in ('completion','scripts','tests','docker','configs')]

    def test_and_reference(self,images):
        worker=images['worker']['id']
        mounts=self.code_mounts()
        env={'PYTHONPATH':'/app:/app/src','PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'}
        tests=self.jobs.job(worker,['-m','pytest','/app/tests','-q','--junitxml=/out/tests.xml'],
            kind='final-tests',entrypoint='/opt/venv/bin/python',extra_mounts=mounts,env=env,timeout=900)
        lint=self.jobs.job(worker,['check','--no-cache','/app/src','/app/scripts','/app/tests','/app/completion','/app/docker/install_snapshot.py'],
            kind='final-lint',entrypoint='/opt/venv/bin/ruff',extra_mounts=mounts,env=env,timeout=300)
        ref=self.jobs.job(worker,['/app/completion/worker.py','reference'],kind='final-reference',
            entrypoint='/opt/venv/bin/python',extra_mounts=mounts,env=env,timeout=300)
        junit=ET.parse(ROOT/tests['result_path']/'tests.xml').getroot()
        suites=list(junit.iter('testsuite'))
        failed=sum(int(x.get('failures','0'))+int(x.get('errors','0')) for x in suites)
        passed=sum(int(x.get('tests','0'))-int(x.get('skipped','0'))-int(x.get('failures','0'))-int(x.get('errors','0')) for x in suites)
        if failed or passed<65:
            raise ProjectError('Current test evidence is incomplete')
        proof=json.loads((ROOT/ref['result_path']/'reference-validation.json').read_text())
        if proof['status']!='passed':
            raise ProjectError('Reference verification did not pass')
        target=folder(PREFIX+'validation')
        for source in (ROOT/ref['result_path']).iterdir():
            if source.is_file() and source.name!='run-status.json':
                shutil.copyfile(source,target/source.name)
        shutil.copyfile(ROOT/tests['result_path']/'tests.xml',target/'tests.xml')
        for record,name in ((tests,'pytest.log'),(lint,'ruff.log')):
            shutil.copyfile(ROOT/record['log_path']/'container.log',target/name)
        evidence=dict(status='passed',utc=utc(),tests_passed=passed,reference_status=proof['status'],
                      tests=tests,lint=lint,reference=ref,images=images,
                      validation_source='current checkout mounted read-only, actual laptop execution')
        write_json(PREFIX+'validation/VALIDATION.json',evidence)
        self.checkpoint([PREFIX+'validation'],'test: save current container tests lint and independent nozzle references','v0.4.0')
        return evidence

    def experiment(self,images,validation):
        protocol=json.loads(safe('configs/study-protocol.json').read_text())
        model=json.loads(safe('configs/stack-selection.json').read_text())['model']
        sources={str(p.relative_to(ROOT)):sha(p) for p in sorted(safe('completion').rglob('*'))
                 if p.is_file() and '__pycache__' not in p.parts}
        sources['configs/study-protocol.json']=sha(safe('configs/study-protocol.json'))
        identity=dict(source_hashes=sources,profile=self.args.profile,images=images,model_sha256=model['sha256'])
        fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        latest=safe('logs/setup/final-active-'+self.args.profile+'.json')
        if latest.exists() and not self.args.new_run:
            state=json.loads(latest.read_text())
            if state['fingerprint']!=fingerprint:
                raise ProjectError('An earlier run has another source/runtime identity. Use --new-run to preserve it and start a new measurement')
            name=state['run_id']
            out=safe(state['result_path'])
            if not out.is_dir():
                raise ProjectError('Saved active-run folder is missing')
        else:
            name=run_id('study-'+self.args.profile)
            out=folder('resutls/'+name)
            state=dict(run_id=name,result_path=str(out.relative_to(ROOT)),fingerprint=fingerprint)
            write_json(str(latest.relative_to(ROOT)),state)
        manifest_path=out/'run-manifest.json'
        manifest=(json.loads(manifest_path.read_text()) if manifest_path.exists() else
                  dict(identity,run_id=name,fingerprint=fingerprint,profile=self.args.profile,
                       source_commit=self.runner.git('rev-parse','HEAD'),started_utc=utc(),
                       protocol=protocol,model=model,planned_requests=216 if self.args.profile=='full' else 12))
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
        validation_path=ROOT/validation['reference']['result_path']
        for filename in ('worked-example.json','reference-validation.json','reference-cases.json','area-mach.png'):
            shutil.copyfile(validation_path/filename,out/filename)
        status=out/'summary.json'
        if status.is_file() and json.loads(status.read_text()).get('status')=='complete':
            print('Reusing the completed measured run:',name,flush=True)
            return out
        if available_ram()<6*1024**3:
            raise ProjectError('Need 6 GiB available RAM before starting the model service')
        self.model_session(images,out,manifest)
        return out

    def model_session(self,images,out,manifest):
        selected=json.loads(safe('configs/stack-selection.json').read_text())
        weights=safe('models/'+selected['model']['filename'])
        profile=json.loads(safe('configs/study-protocol.json').read_text())
        name=run_id('final-llm')
        log=folder('logs/'+name)
        compose_dir=folder('tmp/compose/'+name)
        labels={OWNER_KEY:OWNER,RUN_KEY:name}
        user=f'{os.getuid()}:{os.getgid()}'
        common=dict(user=user,read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            restart='no',init=True,pids_limit=256,tmpfs=['/tmp:rw,nosuid,nodev,size=536870912,mode=1777'],
            labels=labels,networks=['private'],stop_grace_period='10s',pull_policy='never')
        llm=dict(common,image=images['llama']['id'],cpus=6,mem_limit='8g',memswap_limit='8g',
            command=['--model','/models/'+weights.name,'--host','0.0.0.0','--port','8080','--alias','rocket-nozzle-local',
                     '--threads',str(profile['threads']),'--threads-batch',str(profile['threads']),
                     '--ctx-size',str(profile['context_tokens']),'--parallel','1','--n-gpu-layers','0','--jinja',
                     '--chat-template-kwargs','{"enable_thinking":false}'],
            volumes=[{'type':'bind','source':str(weights.parent),'target':'/models','read_only':True}])
        worker_mounts=[{'type':'bind','source':str(p),'target':dest,'read_only':readonly} for p,dest,readonly in self.code_mounts()]
        worker_mounts.append({'type':'bind','source':str(out),'target':'/out'})
        worker=dict(common,image=images['worker']['id'],cpus=2,mem_limit='2g',memswap_limit='2g',
            entrypoint=['/opt/venv/bin/python'],command=['/app/scripts/transport_adapter.py','/app/completion/worker.py','run','--budget-minutes',str(self.args.budget_minutes)],
            environment={'PYTHONPATH':'/app:/app/src','PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1',
                         'ROCKET_RUN_MANIFEST':json.dumps(manifest,sort_keys=True)},volumes=worker_mounts)
        document=dict(services=dict(llm=llm,worker=worker),networks=dict(private=dict(internal=True,labels=labels)))
        config=compose_dir/'compose.json'
        config.write_text(json.dumps(document,indent=2)+'\n')
        prefix=['compose','--project-name',name,'--file',str(config)]
        ids={}
        cleanup=False
        code=None
        write_json('logs/'+name+'/resources.json',dict(owner=OWNER,compose_project=name,compose_file=str(config),status='creating'))
        try:
            self.jobs.call(*(prefix+['create','llm','worker']),timeout=180)
            for service,memory,cpus in [('llm',8*1024**3,6),('worker',2*1024**3,2)]:
                _,ident=self.jobs.call(*(prefix+['ps','--all','--quiet',service]),logged=False)
                ids[service]=ident.strip()
                if not ids[service]:
                    raise ProjectError('Missing created '+service+' container')
                self.jobs.assert_contract(self.jobs.inspect(ids[service]),memory,cpus)
            _,network=self.jobs.call('network','ls','-q','--filter','label=com.docker.compose.project='+name,logged=False)
            if len(network.split())!=1:
                raise ProjectError('Expected one private model network')
            _,raw=self.jobs.call('network','inspect',network.strip(),logged=False)
            item=json.loads(raw)[0]
            if not item['Internal'] or item.get('Labels',{}).get(OWNER_KEY)!=OWNER:
                raise ProjectError('Model network isolation check failed')
            self.jobs.call(*(prefix+['start','llm']),timeout=90)
            code,_=self.jobs.call('start','--attach',ids['worker'],check=False,
                                 timeout=int(self.args.budget_minutes*60+2400))
            item=self.jobs.inspect(ids['worker'])
            if code or item['State']['ExitCode'] or item['State'].get('OOMKilled'):
                raise ProjectError('Experiment worker failed; saved responses are resumable. See '+str(log))
        finally:
            _,text=self.jobs.call(*(prefix+['logs','--no-color']),check=False,logged=False)
            (log/'compose.log').write_text(text)
            self.jobs.call(*(prefix+['down','--remove-orphans','--volumes','--timeout','10']),check=False,timeout=120)
            _,containers=self.jobs.call('ps','-aq','--filter','label=com.docker.compose.project='+name,logged=False)
            _,networks=self.jobs.call('network','ls','-q','--filter','label=com.docker.compose.project='+name,logged=False)
            cleanup=not containers.strip() and not networks.strip()
            write_json('logs/'+name+'/resources.json',dict(owner=OWNER,compose_project=name,compose_file=str(config),status='removed' if cleanup else 'cleanup_failed'))
            (out/'container-lifecycle.json').write_text(json.dumps(dict(session=name,worker_exit=code,
                containers_and_network_removed=cleanup,log_path=str(log.relative_to(ROOT))),indent=2)+'\n')
            if not cleanup:
                raise ProjectError('The current model session did not clean up completely')

    def save_measurements(self,out):
        summary=json.loads((out/'summary.json').read_text())
        target=folder(PREFIX+'evidence/'+out.name)
        for name in ('summary.json','run-manifest.json','schedule.json','answers.csv','human-review.csv',
                     'RESULTS_SUMMARY.md','condition-comparison.png','container-lifecycle.json','execution-overrides.json'):
            source=out/name
            if source.exists():
                shutil.copyfile(source,target/name)
        archive=target/'raw-experiment-evidence.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name in ('requests','responses','scores','transport-failures'):
                source=out/name
                if source.exists():
                    for p in sorted(source.rglob('*')):
                        if p.is_file():
                            z.write(p,p.relative_to(out))
            for name in ('all-answers.json','study-report.html','condition-comparison.png','summary.json','run-manifest.json','execution-overrides.json'):
                if (out/name).exists():
                    z.write(out/name,name)
        shutil.copyfile(out/'RESULTS_SUMMARY.md',safe('docs/RESULTS_SUMMARY.md'))
        self.checkpoint([str(target.relative_to(ROOT)),'docs/RESULTS_SUMMARY.md'],
            'results: save '+summary['status']+' '+summary['profile']+' local LLM versus BM25 RAG evidence',
            'v0.5.0' if summary['status']=='complete' else None)
        return summary

    def render_and_package(self,out,validation,summary):
        from completion.presentation import create_deck, reduce_text_size, validate_deck
        deck=create_deck(out,validation)
        pdf=out/(deck.stem+'.pdf')
        profile_dir=folder('tmp/libreoffice/'+out.name)
        bbox=out/'presentation-text-bounds.xhtml'
        for attempt in range(4):
            pdf.unlink(missing_ok=True)
            self.runner.run(['libreoffice','-env:UserInstallation='+profile_dir.as_uri(),'--headless',
                '--convert-to','pdf:impress_pdf_Export','--outdir',str(out),str(deck)],timeout=600)
            if not pdf.is_file() or pdf.stat().st_size<10000:
                raise ProjectError('LibreOffice did not produce the presentation PDF')
            self.runner.run(['pdftotext','-bbox',str(pdf),str(bbox)],timeout=90)
            try:
                proof=validate_deck(out,bbox)
                break
            except RuntimeError as error:
                if attempt==3 or not any(word in str(error) for word in ('clipping','Rendered text')):
                    raise
                print('Repairing presentation text fit from the current local rendering:',error,flush=True)
                reduce_text_size(deck)
        previews=out/'presentation-preview'
        previews.mkdir(exist_ok=True)
        self.runner.run(['pdftoppm','-png','-scale-to','1600',str(pdf),str(previews/'slide')],timeout=600)
        pngs=list(previews.glob('slide-*.png'))
        if len(pngs)!=proof['slides'] or any(p.stat().st_size<3000 for p in pngs):
            raise ProjectError('Not all presentation pages rendered to readable PNG files')
        # Save the exact final outputs in tracked paths for automatic Git publication.
        destination=folder(PREFIX+'presentation')
        names=[deck.name,pdf.name,'PRESENTER_NOTES.md','presentation-qc.json']
        for name in names:
            shutil.copyfile(out/name,destination/name)
        for name in ('TERM_PAPER.md','TERM_PAPER.html'):
            shutil.copyfile(out/name,safe(PREFIX+name))
        self.write_demo(out)
        handin=out/'Rocket_Propulsion_Final_Handin.zip'
        with zipfile.ZipFile(handin,'w',zipfile.ZIP_DEFLATED) as z:
            for name in [*names,'TERM_PAPER.md','TERM_PAPER.html','RESULTS_SUMMARY.md','summary.json','run-manifest.json',
                         'answers.csv','human-review.csv','study-report.html','condition-comparison.png',
                         'worked-example.json','reference-validation.json','area-mach.png','execution-overrides.json']:
                z.write(out/name,name)
            evidence=safe(PREFIX+'evidence/'+out.name+'/raw-experiment-evidence.zip')
            z.write(evidence,'raw-experiment-evidence.zip')
            z.write(safe('configs/study-protocol.json'),'study-protocol.json')
            z.write(safe(PREFIX+'TRANSPORT_TIMEOUT_REPAIR.md'),'TRANSPORT_TIMEOUT_REPAIR.md')
            z.write(safe(PREFIX+'PROFESSOR_DEMO.md'),'PROFESSOR_DEMO.md')
            z.write(safe(PREFIX+'source-material/Guidelines.pdf'),'Professor_Guidelines.pdf')
        release_dir=folder(PREFIX+'handin')
        shutil.copyfile(handin,release_dir/handin.name)
        outputs={str(p.relative_to(ROOT)):sha(p) for p in [destination/deck.name,destination/pdf.name,
                 safe(PREFIX+'TERM_PAPER.md'),release_dir/handin.name]}
        final=dict(status='FINAL_LOCAL_READY',completed_utc=utc(),profile=summary['profile'],run_id=out.name,
            actual_responses=summary['completed'],scheduled_responses=summary['scheduled'],
            scientific_source_commit=summary['source_commit'],fingerprint=summary['fingerprint'],
            execution_overrides=json.loads((out/'execution-overrides.json').read_text()),
            validation=validation,rendering_qc=proof,files=outputs,
            guideline_mapping={'1 rationale':[2,3],'2 motivation':[4],'3 state of art':[5],
                '4 gap and challenges':[6],'5 approach':[11,12,14],'6 justification':[7,8,10],
                '7 theory and computation':[7,9,10,15,16,17,18],'8 expected versus observed':[19],'9 impact':[20]},
            publication_status='Tracked publication state is verified separately in logs/setup/final-publication.json')
        write_json(PREFIX+'FINAL_MANIFEST.json',final)
        self.checkpoint([PREFIX+'presentation',PREFIX+'TERM_PAPER.md',PREFIX+'TERM_PAPER.html',
                         PREFIX+'PROFESSOR_DEMO.md',PREFIX+'handin',PREFIX+'FINAL_MANIFEST.json'],
            'docs: save measured term paper final presentation and verified hand-in package',
            'v1.0.0' if self.args.profile=='full' else 'v1.0.0-pilot')
        print('\nFINAL_LOCAL_READY',flush=True)
        print('Presentation:',destination/deck.name,flush=True)
        print('PDF:',destination/pdf.name,flush=True)
        print('Hand-in:',release_dir/handin.name,flush=True)
        print('Measured report:',out/'study-report.html',flush=True)
        print('Slide previews:',previews,flush=True)
        print('FINAL_SAVED_AND_PUBLISHED' if self.published else 'FINAL_SAVED_PUBLICATION_PENDING',flush=True)

    def write_demo(self,out):
        text=f'''# Professor demonstration

Project: Local LLM Reliability for Ideal Rocket Nozzles.  
The actual measured run is `{out.name}`. Use slides 1-20 for the talk and 21-25 for demonstration and references.

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git log -6 --oneline
git tag --list
python3 -B scripts/complete_project.py status
xdg-open docs/final/presentation/Rocket_Nozzle_LLM_Presentation_Final.pptx
xdg-open docs/final/presentation/Rocket_Nozzle_LLM_Presentation_Final.pdf
xdg-open "resutls/{out.name}/study-report.html"
cat docs/RESULTS_SUMMARY.md
```

Explain F=mdot Ve+(pe-pa)Ae and the pressure contribution. Show worked-example.json.
Then compare two actual responses in the HTML report. The report retains failures.
All software tests and reference checks are current local executions. The ideal reference does not validate a real engine.
The full experiment has 36 evaluation cases, two conditions and seeds 17,43,89, giving 216 responses.
Physical reasoning and citation-support review remain pending and must not be claimed as completed.

The default command resumes a compatible unfinished full study. Completed inference is reused:

```bash
python3 -B scripts/complete_project.py all
```

Retry only Git publication:

```bash
python3 -B scripts/complete_project.py publish
```

Git history, existing tags and repository visibility are preserved. Push failures leave the final files available locally.
'''
        safe(PREFIX+'PROFESSOR_DEMO.md').write_text(text)

    def all(self):
        self.preflight()
        self.connect_docker()
        self.rendering_tools()
        images=self.images()
        validation=self.test_and_reference(images)
        out=self.experiment(images,validation)
        if not (out/'summary.json').is_file():
            raise ProjectError('No saved study summary; inspect current worker logs')
        summary=self.save_measurements(out)
        if summary['status']!='complete':
            print('PARTIAL_RUN_SAVED:',out,flush=True)
            raise ProjectError('Inference is incomplete. Rerun the same command to resume. No final success tag was created')
        self.render_and_package(out,validation,summary)
        return 0 if self.published or self.args.local_only else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='all',choices=['all','status','publish','cleanup'])
    parser.add_argument('--profile',choices=['full','presentation'],default='full')
    parser.add_argument('--budget-minutes',type=float,default=720)
    parser.add_argument('--local-only',action='store_true')
    parser.add_argument('--new-run',action='store_true')
    args=parser.parse_args()
    if not 1<=args.budget_minutes<=1440:
        parser.error('--budget-minutes must be between 1 and 1440')
    workflow=Workflow(args)
    lock_path=folder('logs/setup')/'project-command.lock'
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another project command is active. No resources were changed.')
        def stop(signum,frame):
            raise KeyboardInterrupt('Stop requested; completed responses stay saved')
        signal.signal(signal.SIGINT,stop)
        signal.signal(signal.SIGTERM,stop)
        try:
            if args.command=='status':
                for relative in ('docs/final/FINAL_MANIFEST.json','logs/setup/final-publication.json',
                                 'logs/setup/final-active-full.json','logs/setup/final-active-presentation.json'):
                    if safe(relative).is_file():
                        print(relative+'\n'+safe(relative).read_text())
                return 0
            if args.command=='publish':
                return 0 if workflow.publish() else 2
            if args.command=='cleanup':
                workflow.connect_docker()
                return 0
            return workflow.all()
        except (ProjectError,OSError,subprocess.SubprocessError,ValueError,KeyError,RuntimeError) as error:
            write_json('logs/setup/final-last-error.json',dict(error_type=type(error).__name__,error=str(error),utc=utc()))
            print('\nSAVED_PROGRESS; completion stopped:',error,flush=True)
            print('Inspect logs/setup/final-last-error.json and rerun the same command after correcting the reported pre-flight issue.',flush=True)
            return 1
        except KeyboardInterrupt:
            print('\nINTERRUPTED_SAFELY: saved responses will resume on the next run.',flush=True)
            return 130
        finally:
            if workflow.jobs is not None:
                try:
                    workflow.jobs.cleanup()
                except (ProjectError,OSError) as error:
                    print('CLEANUP_REQUIRES_ATTENTION:',error,flush=True)
            workflow.stop_keepalive.set()


if __name__=='__main__':
    raise SystemExit(main())
