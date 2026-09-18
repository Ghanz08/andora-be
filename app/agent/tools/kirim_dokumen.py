import json
import os
import smtplib
from email.message import EmailMessage
from typing import Literal

from livekit.agents import function_tool, RunContext


def _send_email_smtp(to_email: str, file_path: str, subject: str, body: str) -> None:
    """Kirim email dengan attachment lewat SMTP."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM_EMAIL")
    msg["To"] = to_email
    msg.set_content(body)

    with open(file_path, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(file_path)

    msg.add_attachment(
        file_data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=file_name,
    )

    with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", 587))) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)


@function_tool()
async def kirim_dokumen(
    context: RunContext,
    nama_dokumen: str,
    channel: Literal["email", "whatsapp"],
    tujuan: str,
) -> str:
    """
    Kirim dokumen yang sudah dibuat sebelumnya ke email atau WhatsApp.
    Panggil tool ini SETELAH eksekusi_cetak_dokumen berhasil, dan user
    sudah konfirmasi ingin mengirim serta menyebutkan tujuannya.

    Args:
        nama_dokumen: Nama dokumen dalam format snake_case, sama seperti
            yang dipakai saat cetak, misal: "surat_pernyataan_5_poin".
        channel: "email" atau "whatsapp", sesuai pilihan user.
        tujuan: Alamat email, atau nomor WhatsApp (format internasional,
            misal "628123456789") sesuai yang disebutkan user.
    """
    # Ambil path dokumen yang udah dicetak sebelumnya di sesi ini
    if not hasattr(context, "userdata") or context.userdata is None:
        return "Error sistem: tidak ada data sesi tersimpan."

    file_path = context.userdata.generated_documents.get(nama_dokumen)

    if not file_path or not os.path.exists(file_path):
        return (
            f"Dokumen '{nama_dokumen}' belum ditemukan atau belum dicetak. "
            "TUGAS AI: Beritahu user bahwa dokumen perlu dibuat dulu sebelum dikirim."
        )

    if channel == "email":
        try:
            _send_email_smtp(
                to_email=tujuan,
                file_path=file_path,
                subject=f"Dokumen: {nama_dokumen.replace('_', ' ').title()}",
                body=f"Berikut dokumen {nama_dokumen.replace('_', ' ')} yang dibuat melalui Andora.",
            )
            return (
                f"Dokumen berhasil dikirim ke email {tujuan}.\n\n"
                f"TUGAS AI: Beritahu user dengan nada gembira bahwa dokumennya "
                f"sudah terkirim ke email tersebut."
            )
        except Exception as e:
            return (
                f"Gagal mengirim email: {str(e)}\n\n"
                f"TUGAS AI: Beritahu user bahwa pengiriman gagal, minta maaf, "
                f"dan sarankan coba lagi atau cek alamat email."
            )

    elif channel == "whatsapp":
        # WhatsApp gak bisa dikirim langsung dari backend (lihat catatan
        # PERUBAHAN.md), jadi kita kirim SIGNAL ke FE lewat data channel
        # LiveKit, supaya FE buka Intent WhatsApp dengan file siap kirim.
        try:
            payload = {
                "action": "OPEN_WHATSAPP_INTENT",
                "payload": {
                    "phone_number": tujuan,
                    "file_path": file_path,
                    "caption": f"Dokumen {nama_dokumen.replace('_', ' ')} dari Andora",
                },
            }

            if context.room:
                await context.room.local_participant.publish_data(
                    json.dumps(payload).encode()
                )

            return (
                f"Sistem sudah menyiapkan WhatsApp dengan dokumen terlampir "
                f"ke nomor {tujuan}.\n\n"
                f"TUGAS AI: Beritahu user bahwa WhatsApp akan terbuka dengan "
                f"dokumen dan pesan yang sudah siap, dan minta user untuk "
                f"menekan tombol kirim di WhatsApp untuk menyelesaikan."
            )
        except Exception as e:
            return f"Gagal menyiapkan pengiriman WhatsApp: {str(e)}"

    return "Channel pengiriman tidak dikenali."