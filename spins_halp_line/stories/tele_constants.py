from spins_halp_line.media.common import Clavae_Puzzle_Image_1, Karen_Puzzle_Image_1, Telemarketopia_Logo, \
    Clavae_Final_Puzzle_Image_1, Clavae_Final_Puzzle_Image_2, Karen_Final_Puzzle_Image_1, Karen_Final_Puzzle_Image_2
from spins_halp_line.actions.twilio import TextTask


#
#  _______        _
# |__   __|      | |
#    | | _____  _| |_ ___
#    | |/ _ \ \/ / __/ __|
#    | |  __/>  <| |_\__ \
#    |_|\___/_/\_\\__|___/
#

class Clavae1(TextTask):
    Text = "Call me at +1-510-256-7710 to learn the horrible truth about Babyface's Telemarketopia!\n - Clavae"
    From_Number_Label = 'clavae_1'


class Clavae2(TextTask):
    Text = """"
Once you fill this in, this puzzle should give you a five-digit code to get into the database at +1-510-256-7705!
- Clavae"""
    From_Number_Label = 'clavae_2'
    Image = Clavae_Puzzle_Image_1


class Karen1(TextTask):
    Text = "Solving this puzzle will give you the next phone number to call and prove you're Telemarketopia material!"
    From_Number_Label = 'karen_1'
    Image = Karen_Puzzle_Image_1


class Karen2(TextTask):
    Text = "Please call +1-510-256-7675 to continue learning about the exciting opportunities you'll have at Telemarketopia!"
    From_Number_Label = 'karen_2'
    Image = Telemarketopia_Logo


class ConfWait(TextTask):
    Text = "Our systems are working on bisecting the quantum lagrange points, we'll connect you as soon as we can!"
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class ConfReady(TextTask):
    Text = "HEY!\nHey.\nI've got that person you wanted to talk to! Just text back anything when you're ready!!"
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo

class ConfReadyTwo(TextTask):
    Text = "Are you still there? Send me any text at all back to us if you're ready and, if you aren't ready now, we'll try again later."
    From_Number_Label = 'conference'


class ConfUnReadyIfReply(TextTask):
    Text = "Oh no, I'm sorry. It looks like the person we paired you up with was less enthusiastic than we expected. Give us some time to find someone else..."
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class ConfUnReadyIfNoReply(TextTask):
    Text = "Oh no! The lagrange solution has become inverted! We're going to have to wait a little longer."
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class KPostConfOptions(TextTask):
    Text = """
Text one of the following to decide what you will do next:
Text 1 if: I believe I have recruited the other team. Hooray! I will request a promotion from Telemarketopia!
Text 2 if: The other team has convinced me to open a Doortal to release Madame Clavae. 
Text 3 if: Attempt to Destroy Telemarketopia!!"""
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class CPostConfOptions(TextTask):
    Text = """
Text one of the following to decide what you will do next:
Text 1 if: The other team has convinced me to join Telemarketopia! I release my body and go forth in search of personal gain and power.
Text 2 if: I believe I have convinced the other team to open a Doortal. Hooray! I’ll tell Madame Clavae the good news.
Text 3 if: Attempt to Destroy Telemarketopia!!"""
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class CFinalPuzzle1(TextTask):
    Text = """
To break into the central AI Database and hit the manual self-destruct button, you’ll need to enter the correct passcode. Your only clues are these cryptic notes, left inside one of the database passages.
    """
    From_Number_Label = 'final'
    Image = Clavae_Final_Puzzle_Image_1


class CFinalPuzzle2(TextTask):
    Text = """
You’ll need to work together in another voice conference to finish. One of your team needs to text the correct passcode (AND ONLY THE PASSCODE NUMBER) to +1-510-256-7740.
    """
    From_Number_Label = 'final'
    Image = Clavae_Final_Puzzle_Image_2


class KFinalPuzzle1(TextTask):
    Text = """
To break into the central AI Database and hit the manual self-destruct button, you’ll need to enter the correct passcode. Your only clues are these cryptic notes, left inside one of the database passages.
    """
    From_Number_Label = 'final'
    Image = Karen_Final_Puzzle_Image_1


class KFinalPuzzle2(TextTask):
    Text = """
You’ll need to work together in another voice conference to finish. One of your team needs to text the correct passcode (AND ONLY THE PASSCODE NUMBER) to +1-510-256-7740.
    """
    From_Number_Label = 'final'
    Image = Karen_Final_Puzzle_Image_2


# state keys
Telemarketopia_Name = "Telemarketopia"

# paths
Path_Clavae = 'Clavae'
Path_Karen = 'Karen'

# _got_text = 'got_text'
_ready_for_conf = 'player_responded_to_conf_invite'
_path = 'path'
