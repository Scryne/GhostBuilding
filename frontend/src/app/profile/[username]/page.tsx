import type { Metadata } from "next";
import ProfileView from "./ProfileView";

interface ProfilePageProps {
  params: { username: string };
}

export async function generateMetadata({
  params,
}: ProfilePageProps): Promise<Metadata> {
  return {
    title: `${params.username} Profili`,
    description: `${params.username} kullanıcısının GhostBuilding profili, istatistikleri ve rozetleri.`,
  };
}

export default function ProfilePage({ params }: ProfilePageProps) {
  return <ProfileView username={params.username} />;
}
