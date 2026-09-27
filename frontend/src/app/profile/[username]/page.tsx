import type { Metadata } from "next";
import ProfileView from "./ProfileView";

interface ProfilePageProps {
  // Next 15+: dinamik parametreler Promise olarak gelir.
  params: Promise<{ username: string }>;
}

export async function generateMetadata({ params }: ProfilePageProps): Promise<Metadata> {
  const { username } = await params;
  return {
    title: `${username} profili`,
    description: `${username} kullanıcısının GhostBuilding doğrulama geçmişi ve güven puanı.`,
    robots: { index: false, follow: false },
  };
}

export default async function ProfilePage({ params }: ProfilePageProps) {
  const { username } = await params;
  return <ProfileView username={decodeURIComponent(username)} />;
}
