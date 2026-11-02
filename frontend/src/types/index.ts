export interface User {
  id: number;
  full_name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  status: string;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectMember {
  id: number;
  project_id: number;
  user_id: number;
  full_name: string;
  email: string;
  role: string;
  responsibility: string | null;
  membership_status: string;
  joined_at: string;
}