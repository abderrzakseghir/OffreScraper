import { NextResponse } from 'next/server';
import { extractCode, userPath } from '@/lib/auth';
import { readJSON, writeJSON } from '@/lib/storage';
import type { UserSettings, UserProfile, JobOffer } from '@/lib/types';
import { DEFAULT_PROFILE } from '@/lib/defaults';
import { execFile } from 'child_process';
import path from 'path';

function runPythonGenerate(input: object): Promise<{ success: boolean; latex?: string; error?: string }> {
  return new Promise((resolve, reject) => {
    const bridgePath = path.resolve(process.cwd(), '..', 'bridge_generate.py');
    const child = execFile('python', [bridgePath], {
      cwd: path.resolve(process.cwd(), '..'),
      timeout: 120_000,
      maxBuffer: 5 * 1024 * 1024,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || error.message));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error('Invalid JSON from generator'));
      }
    });

    child.stdin?.write(JSON.stringify(input));
    child.stdin?.end();
  });
}

export async function POST(request: Request) {
  const code = extractCode(request);
  if (!code) return NextResponse.json({ success: false, error: 'Non authentifié' }, { status: 401 });

  const { offerId } = await request.json();
  if (!offerId) return NextResponse.json({ success: false, error: "ID d'offre requis" }, { status: 400 });

  const settings = await readJSON<UserSettings>(userPath(code, 'settings.json'));
  if (!settings?.apiKey) {
    return NextResponse.json({ success: false, error: 'Clé API non configurée' }, { status: 400 });
  }

  const profile = await readJSON<UserProfile>(userPath(code, 'profile.json')) ?? DEFAULT_PROFILE;
  const offers = await readJSON<JobOffer[]>(userPath(code, 'offers.json')) ?? [];
  const offer = offers.find(o => o.id === offerId);

  if (!offer) return NextResponse.json({ success: false, error: 'Offre introuvable' }, { status: 404 });

  try {
    const result = await runPythonGenerate({
      action: 'cover-letter',
      offer: {
        title: offer.title,
        company: offer.company,
        description: offer.description,
        location: offer.location,
        contractType: offer.contractType,
        technologies: offer.technologies,
      },
      profile,
      api_key: settings.apiKey,
    });

    if (!result.success || !result.latex) {
      return NextResponse.json({ success: false, error: result.error || 'Génération échouée' }, { status: 500 });
    }

    // Save the generated LaTeX into the offer
    const idx = offers.findIndex(o => o.id === offerId);
    if (idx !== -1) {
      offers[idx].coverLetterLatex = result.latex;
      await writeJSON(userPath(code, 'offers.json'), offers);
    }

    return NextResponse.json({ success: true, data: { latex: result.latex } });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Erreur inconnue';
    return NextResponse.json({ success: false, error: msg }, { status: 500 });
  }
}
