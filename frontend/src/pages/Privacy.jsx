import React from 'react';
import { EyeOff, Lock, ShieldCheck, UserCheck } from 'lucide-react';

const Privacy = () => (
  <div className="page-stack narrow-page">
    <section className="section-heading"><div><span className="eyebrow">TRUST & SAFETY</span><h2>Privacy & consent</h2><p>How SAHAYAK uses AI while keeping human judgement at the centre.</p></div></section>
    <div className="privacy-hero"><div className="privacy-icon"><ShieldCheck size={28}/></div><div><strong>Human-led by design</strong><span>AI outputs are decision support, never autonomous decisions.</span></div></div>
    <section className="privacy-grid">
      <PrivacyItem icon={Lock} title="AI-assisted assessment">SAHAYAK uses machine learning to help responders triage cases. Narratives and audio can be analyzed to identify potential vulnerability signals.</PrivacyItem>
      <PrivacyItem icon={EyeOff} title="Purpose limitation">Information processed by this system is intended for vulnerability assessment and triage and is not intended for unrelated purposes.</PrivacyItem>
      <PrivacyItem icon={UserCheck} title="Human-in-the-loop">Every AI-generated assessment requires review by an authorized human responder before action or support recommendations are finalized.</PrivacyItem>
    </section>
    <div className="notice-box"><strong>Prototype notice</strong><p>This is an operational prototype. AI can have limitations and outputs should always be cross-verified through direct human interaction.</p></div>
  </div>
);
const PrivacyItem=({icon:Icon,title,children})=><article className="privacy-item"><div className="privacy-item-icon"><Icon size={19}/></div><div><h3>{title}</h3><p>{children}</p></div></article>;
export default Privacy;
