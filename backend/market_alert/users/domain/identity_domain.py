""" Constantes e helpers para fluxos de verificação de identidade """

from market_alert.enums.enums_users import VerificationKind


#Mapeia o canal de entrada para o tipo de verificação do domínio.
VERIFICATION_CHANNEL_TO_KIND = {
    "email": VerificationKind.email,
    "phone_number": VerificationKind.phone_number,
}
