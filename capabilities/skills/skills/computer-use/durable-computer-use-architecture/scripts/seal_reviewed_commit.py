#!/usr/bin/env python3
"""Deterministically seal a reviewed Git commit.

Requires two structured review JSON files with passed=true and must_fix=[].
Exports only Git-tracked content, adds verbatim reviews, manifest and SHA256SUMS,
and normalizes uid/gid/mtime. Adapt manifest_fields() for the project class.
"""
from __future__ import annotations
import argparse,gzip,hashlib,io,json,os,subprocess,tarfile,tempfile
from pathlib import Path

def sha(p:Path)->str:
 d=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): d.update(b)
 return d.hexdigest()
def review(p:Path)->dict:
 v=json.loads(p.read_text())
 if v.get("passed") is not True or v.get("must_fix")!=[]: raise SystemExit(f"review gate failed: {p}")
 return v
def archive(root:Path,out:Path):
 with out.open("wb") as raw, gzip.GzipFile(filename="",mode="wb",fileobj=raw,mtime=0) as gz, tarfile.open(fileobj=gz,mode="w",format=tarfile.PAX_FORMAT) as t:
  for p in sorted(root.rglob("*"),key=lambda x:x.relative_to(root).as_posix()):
   info=t.gettarinfo(str(p),arcname=f"sealed/{p.relative_to(root).as_posix()}"); info.uid=info.gid=0; info.uname=info.gname="root"; info.mtime=0
   if p.is_file():
    with p.open("rb") as f:t.addfile(info,f)
   else:t.addfile(info)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--repo",type=Path,required=True); ap.add_argument("--commit",required=True)
 ap.add_argument("--review-a",type=Path,required=True); ap.add_argument("--review-b",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
 a=ap.parse_args(); commit=subprocess.check_output(["git","rev-parse",a.commit],cwd=a.repo,text=True).strip()
 if subprocess.check_output(["git","status","--porcelain=v1"],cwd=a.repo,text=True).strip(): raise SystemExit("dirty worktree")
 reviews=[review(a.review_a),review(a.review_b)]
 with tempfile.TemporaryDirectory(prefix="seal-") as raw:
  stage=Path(raw)/"stage"; stage.mkdir(); data=subprocess.check_output(["git","archive","--format=tar",commit],cwd=a.repo)
  with tarfile.open(fileobj=io.BytesIO(data),mode="r:") as src: src.extractall(stage,filter="data")
  rd=stage/"reviews"; rd.mkdir()
  for i,v in enumerate(reviews,1):(rd/f"review-{i}.json").write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
  (stage/"FINAL_MANIFEST.json").write_text(json.dumps({"source_commit":commit,"reviewers_passed":[v["passed"] for v in reviews],"reviewer_must_fix":[v["must_fix"] for v in reviews]},indent=2,sort_keys=True)+"\n")
  rows=[f"{sha(p)}  {p.relative_to(stage).as_posix()}" for p in sorted(stage.rglob("*")) if p.is_file() and p.name!="SHA256SUMS"]
  (stage/"SHA256SUMS").write_text("\n".join(rows)+"\n"); a.output.parent.mkdir(parents=True,exist_ok=True); archive(stage,a.output)
 os.chmod(a.output,0o444); print(json.dumps({"archive":str(a.output),"sha256":sha(a.output),"source_commit":commit},sort_keys=True))
if __name__=="__main__":main()
