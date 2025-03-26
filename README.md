# Hook Userbot

**Hook** is a powerful and flexible Telegram bot designed to automate tasks, improve the user experience, and provide extensive customization options. Hook is based on modern technologies and offers a user-friendly web interface for installation, support for inline forms, galleries, and more.

<b>Attention:If you are paranoid, this userbot may not be suitable for you. Hook is not a virus, but it can be used for malicious purposes. You are solely responsible for the actions of your account.

---

## Installation

### Installation via script (recommended)
For a quick and easy installation, run the following command from under **root** and follow the instructions of the installer:

```bash
wget https://raw.githubusercontent.com/HookDev-arch/Hook/refs/heads/master/install.sh && chmod 777 install.sh && ./install.sh
```

### Manual installation (without script)
If you prefer to install the Hook manually:

```bash
apt update && apt install git libcairo2 -y && git clone https://github.com/HookDev-arch/Hook && cd Hook && pip install -r requirements.txt && python3 -m hook --root
```

- If you are using a VPS/VDS, add `--proxy-pass` to the end of the command to open an SSH tunnel to the Hook web interface.
- To configure it in the console without a web interface, use `--no-web'.

### Installation Details
- **Web interface**: After launching with `--proxy-pass`, you will receive a link for configuration via the browser (for example, `https://<unique-id>.lhr.life`).
- **QR Code**: To log in, scan the QR code via Telegram on your device.

---

## Requirements
- Python 3.8+
- API_ID and API_HASH from [my.telegram.org/apps ](https://my.telegram.org/apps )
- Installed dependencies (`requirements.txt `)

---

## Features
Hook offers many features for users and developers.:

- **Interactive forms**: Control the robot via buttons, forget about manual input.
- **Galleries**: View photos directly in Telegram with easy navigation.
- **Inline Commands**: Share the Hook functionality with your friends via the @bot.
- **Message Logs**: Receive error traceback directly in the chat.
- **Multi-account support**: Use the Hook from your primary or secondary account.

## Changes and Benefits
- Support for the last layer of Telegram (reactions, video stickers, etc.).
- Improved security with entity caching and flexible rules.
- 🎨 Updated interface and user-friendliness.
- New and improved basic modules.
- Quick error correction.
- Compatible with FTG, GeekTG, and Dragon Usbot modules, as well as Hikka.

---

## Documentation
- For developers: [dev.hook.pw ](https://dev.hook.pw ) (under development).
- For users: [hook.pw ](https://hook.pw ) (under development).

While the documentation is under construction, you can contact the [official support chat](#support) for help.

---

## Support
If you have any questions or problems, please join our community.:
- Telegram: [t.me/hook_support](https://t.me/hookdev_arch_chat).

---

## Credits and acknowledgements
Hook would not have been possible without the contributions of the following people and projects:
- [Hikariatama](https://github.com/hikariatama ) — for the original Hikka project that inspired us.
- [Hackintosh5](https://gitlab.com/hackintosh5 ) — for FTG, which has become the basis for many pilots.
- [Lonami](https://t.me/lonami ) — for Telethon, the basis of Hook-TL.
- [Dan](https://github.com/delivrance ) — for Pyrogram, used in some parts of the project.
- To the Hook community, for testing, feedback, and support.

Special thanks to everyone who participated in testing and helped debug the code!

---

## Warning
The hook is provided "as is". The developers are not responsible for any problems caused by the use of the userbot, including:
- Account bans.
- Deletion of messages by Telegram algorithms.
- Session leaks due to third-party modules.

**Recommendations:**
- Enable API flood protection (`.api_fw_protection`).
- Do not install many third-party modules at once.
- Read the [Telegram API Terms and Conditions](https://core.telegram.org/api/terms ).

By using Hook, you agree that all actions of your account are your responsibility.

---

### Hook — your Telegram assistant
Hook is designed for those who want more control and automation in Telegram. Install it, customize it for yourself and enjoy a new level of possibilities!
