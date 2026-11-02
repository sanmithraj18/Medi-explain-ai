export interface User {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  is_admin?: boolean;
}

export interface Subscription {
  id: string;
  user_id: string;
  plan_name: string;
  amount: number;
  currency: string;
  trial_start_date?: string;
  trial_end_date?: string;
  subscription_status: SubscriptionStatus;
  gateway_subscription_id?: string;
  billing_start_date?: string;
  next_billing_date?: string;
  cancellation_date?: string;
  created_at: string;
  updated_at: string;
}

export type SubscriptionStatus =
  | 'TRIAL_ACTIVE'
  | 'TRIAL_EXPIRED'
  | 'AUTHORIZATION_PENDING'
  | 'ACTIVE'
  | 'PAYMENT_PENDING'
  | 'PAYMENT_FAILED'
  | 'CANCELLED'
  | 'HALTED'
  | 'EXPIRED';

export interface MedicalReport {
  id: string;
  user_id: string;
  report_name: string;
  file_path: string;
  file_type: 'pdf' | 'jpg' | 'jpeg' | 'png';
  upload_date: string;
  processing_status: ProcessingStatus;
  processing_error?: string;
  created_at: string;
}

export type ProcessingStatus =
  | 'PENDING'
  | 'EXTRACTING'
  | 'EXTRACTED'
  | 'ANALYZING'
  | 'COMPLETED'
  | 'FAILED'
  | 'NEEDS_REVIEW';

export interface ExtractedParameter {
  id: string;
  report_id: string;
  parameter_name: string;
  observed_value: string;
  unit?: string;
  reference_min?: number;
  reference_max?: number;
  reference_text?: string;
  laboratory_flag?: 'H' | 'L' | 'N' | 'CRITICAL';
  extraction_confidence?: number;
  needs_user_review: boolean;
}

export interface ReportAnalysis {
  id: string;
  report_id: string;
  overall_summary: OverallSummary;
  detailed_explanation: Record<string, ParameterExplanation>;
  limitations?: string[];
  ai_model: string;
  created_at: string;
}

export interface OverallSummary {
  report_type: string;
  overall_assessment: string;
  parameters_within_range: string[];
  parameters_outside_range: string[];
  parameters_unclassified?: string[];
  potentially_critical_flags: string[];
  missing_information: string[];
  key_limitations: string[];
  disclaimer: string;
  doctor_discussion_questions: string[];
}

export interface ParameterExplanation {
  parameter_name: string;
  observed_value: string;
  unit?: string | null;
  reference_range?: string | null;
  classification:
    | 'WITHIN_RANGE'
    | 'BELOW_RANGE'
    | 'ABOVE_RANGE'
    | 'CRITICAL'
    | 'SIGNIFICANTLY_BELOW'
    | 'SIGNIFICANTLY_ABOVE'
    | 'INCOMPLETE_ASSESSMENT'
    | 'PEDIATRIC_INTERPRETATION_REQUIRED'
    | 'RANGE_UNAVAILABLE'
    | 'NOT_CLASSIFIED'
    | 'UNKNOWN'
    | 'UNCONFIRMED_OCR_VALUE';
  what_it_measures: string;
  simple_explanation: string;
  contextual_limitations: string;
  when_to_seek_attention: string;
  doctor_questions: string[];
  disclaimer: string;
  is_contextual_threshold?: boolean;
  clinical_source?: string | null;
  contextual_notes?: string | null;
}

export interface DoctorQuestion {
  id: string;
  report_id: string;
  question: string;
  question_order: number;
  discussion_status: 'PENDING' | 'DISCUSSED';
  created_at: string;
}

export interface Payment {
  id: string;
  user_id: string;
  gateway_payment_id: string;
  amount: number;
  currency: string;
  payment_status: string;
  payment_date?: string;
  created_at: string;
}
