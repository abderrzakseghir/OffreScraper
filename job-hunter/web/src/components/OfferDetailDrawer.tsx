'use client';

import { useState } from 'react';
import type { JobOffer } from '@/lib/types';

interface Props {
  offer: JobOffer;
  onClose: () => void;
  onUpdateOffer: (id: string, updates: Partial<JobOffer>) => void;
}

const STATUS_LABELS: Record<string, string> = {
  new: 'Nouvelle',
  viewed: 'Vue',
  applied: 'Postulée',
  rejected: 'Rejetée',
};

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  viewed: 'bg-gray-100 text-gray-700',
  applied: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
};

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-400 text-sm">Non scoré</span>;
  let color = 'bg-red-100 text-red-700';
  if (score >= 80) color = 'bg-green-100 text-green-700';
  else if (score >= 60) color = 'bg-yellow-100 text-yellow-700';
  else if (score >= 40) color = 'bg-orange-100 text-orange-700';
  return (
    <div className="flex items-center gap-3">
      <span className={`px-3 py-1 rounded-full text-sm font-bold ${color}`}>{score}/100</span>
      <div className="flex-1 max-w-48 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${score >= 80 ? 'bg-green-500' : score >= 60 ? 'bg-yellow-500' : score >= 40 ? 'bg-orange-500' : 'bg-red-500'}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

function CodeBlock({ code, title, onGenerate, generating }: {
  code: string | null;
  title: string;
  onGenerate: () => void;
  generating: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!code) return;
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!code) {
    return (
      <div className="border border-dashed border-gray-300 rounded-lg p-6 text-center">
        <p className="text-gray-500 mb-3">{title} non encore généré(e) pour cette offre</p>
        <button
          onClick={onGenerate}
          disabled={generating}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {generating ? 'Génération en cours...' : `Générer ${title}`}
        </button>
      </div>
    );
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-100 border-b border-gray-200">
        <span className="text-sm font-medium text-gray-700">{title}</span>
        <div className="flex gap-2">
          <button
            onClick={onGenerate}
            disabled={generating}
            className="px-3 py-1 text-xs text-orange-600 hover:bg-orange-50 rounded transition disabled:opacity-50"
          >
            {generating ? '...' : '↻ Régénérer'}
          </button>
          <button
            onClick={handleCopy}
            className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition"
          >
            {copied ? '✓ Copié !' : 'Copier le code'}
          </button>
        </div>
      </div>
      <pre className="bg-gray-900 text-green-400 p-4 text-xs font-mono whitespace-pre-wrap overflow-auto max-h-96 leading-relaxed">
        {code}
      </pre>
    </div>
  );
}

export default function OfferDetailDrawer({ offer, onClose, onUpdateOffer }: Props) {
  const [cvGenerating, setCvGenerating] = useState(false);
  const [letterGenerating, setLetterGenerating] = useState(false);
  const [localOffer, setLocalOffer] = useState(offer);

  async function handleGenerateCV() {
    setCvGenerating(true);
    try {
      const res = await fetch('/api/generate/cv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offerId: offer.id }),
      });
      const data = await res.json();
      if (data.success) {
        const updated = { cvLatex: data.data.latex };
        setLocalOffer(prev => ({ ...prev, ...updated }));
        onUpdateOffer(offer.id, updated);
      } else {
        alert(data.error || 'Erreur lors de la génération du CV');
      }
    } catch {
      alert('Erreur réseau');
    } finally {
      setCvGenerating(false);
    }
  }

  async function handleGenerateLetter() {
    setLetterGenerating(true);
    try {
      const res = await fetch('/api/generate/cover-letter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offerId: offer.id }),
      });
      const data = await res.json();
      if (data.success) {
        const updated = { coverLetterLatex: data.data.latex };
        setLocalOffer(prev => ({ ...prev, ...updated }));
        onUpdateOffer(offer.id, updated);
      } else {
        alert(data.error || 'Erreur lors de la génération de la lettre');
      }
    } catch {
      alert('Erreur réseau');
    } finally {
      setLetterGenerating(false);
    }
  }

  const sourceUrl = localOffer.sourceUrl || localOffer.url;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/40" onClick={onClose} />

      {/* Drawer */}
      <div className="w-full max-w-3xl bg-white shadow-2xl overflow-y-auto animate-slide-in">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-6 py-4 flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-gray-900 truncate">{localOffer.title}</h2>
            <p className="text-sm text-gray-600 mt-0.5">{localOffer.company} — {localOffer.location}</p>
          </div>
          <button
            onClick={onClose}
            className="ml-4 p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition flex-shrink-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Informations de l'offre */}
          <section>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Informations de l&apos;offre</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs font-medium text-gray-500 block mb-1">Entreprise</span>
                <span className="text-sm text-gray-900">{localOffer.company}</span>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-500 block mb-1">Localisation</span>
                <span className="text-sm text-gray-900">{localOffer.location || '—'}</span>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-500 block mb-1">Type de contrat</span>
                <span className="text-sm text-gray-900">{localOffer.contractType || '—'}</span>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-500 block mb-1">Date de scraping</span>
                <span className="text-sm text-gray-900">
                  {localOffer.dateScraped ? new Date(localOffer.dateScraped).toLocaleDateString('fr-FR') : '—'}
                </span>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-500 block mb-1">Source</span>
                <span className="text-sm text-gray-900">{localOffer.source || '—'}</span>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-500 block mb-1">Salaire</span>
                <span className="text-sm text-gray-900">{localOffer.salary || '—'}</span>
              </div>
            </div>

            {/* Score IA */}
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-500 block mb-2">Score IA</span>
              <ScoreBadge score={localOffer.score} />
              {localOffer.scoreDetails && (
                <p className="text-xs text-gray-500 mt-1">{localOffer.scoreDetails}</p>
              )}
            </div>

            {/* Statut */}
            <div className="mt-4">
              <span className="text-xs font-medium text-gray-500 block mb-1">Statut de candidature</span>
              <select
                value={localOffer.status}
                onChange={e => {
                  const newStatus = e.target.value as JobOffer['status'];
                  setLocalOffer(prev => ({ ...prev, status: newStatus }));
                  onUpdateOffer(offer.id, { status: newStatus });
                }}
                className={`px-3 py-1.5 rounded-full text-sm font-medium ${STATUS_COLORS[localOffer.status]} border-0 cursor-pointer`}
              >
                {Object.entries(STATUS_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>

            {/* Technologies */}
            {localOffer.technologies.length > 0 && (
              <div className="mt-4">
                <span className="text-xs font-medium text-gray-500 block mb-2">Technologies</span>
                <div className="flex flex-wrap gap-1.5">
                  {localOffer.technologies.map(t => (
                    <span key={t} className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs font-medium">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Lien vers l'offre originale */}
            {sourceUrl && sourceUrl !== '#' && (
              <div className="mt-4">
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  Voir l&apos;offre originale
                </a>
              </div>
            )}
          </section>

          {/* Description */}
          {localOffer.description && (
            <section>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Description</h3>
              <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                {localOffer.description}
              </div>
            </section>
          )}

          {/* CV LaTeX */}
          <section>
            <h3 className="text-lg font-semibold text-gray-900 mb-3">CV LaTeX</h3>
            <CodeBlock
              code={localOffer.cvLatex}
              title="CV LaTeX"
              onGenerate={handleGenerateCV}
              generating={cvGenerating}
            />
          </section>

          {/* Lettre de motivation LaTeX */}
          <section>
            <h3 className="text-lg font-semibold text-gray-900 mb-3">Lettre de motivation LaTeX</h3>
            <CodeBlock
              code={localOffer.coverLetterLatex}
              title="Lettre de motivation"
              onGenerate={handleGenerateLetter}
              generating={letterGenerating}
            />
          </section>
        </div>
      </div>
    </div>
  );
}
