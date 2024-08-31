from pydub import AudioSegment
from pydub.silence import split_on_silence


class Numbers:
    lang = "UZ"

    lang_map = {
        "UZ": {"thousand": "ming", "million": "million", "billion": "milliard", "trillion": "trillion", "one": "bir",
               "two": "ikki", "three": "uch", "four": "to'rt", "five": "besh", "six": "olti", "seven": "yetti",
               "eight": "sakkiz", "nine": "to'qqiz", "ten": "o'n", "twenty": "yigirma", "thirty": "o'ttiz",
               "forty": "qirq", "fifty": "ellik", "sixty": "oltmish", "seventy": "yetmish", "eighty": "sakson",
               "ninety": "to'qson", "hundred": "yuz", "whole": "butun", },
        "UZ_CYRILLIC": {"thousand": "минг", "million": "миллион", "billion": "миллиард", "trillion": "трилион",
                        "one": "бир", "two": "икки", "three": "уч", "four": "тўрт", "five": "беш", "six": "олти",
                        "seven": "етти", "eight": "саккиз", "nine": "тўққиз", "ten": "ўн", "twenty": "йигирма",
                        "thirty": "ўттиз", "forty": "қирқ", "fifty": "эллик", "sixty": "олтмиш", "seventy": "етмиш",
                        "eighty": "саксон", "ninety": "тўқсон", "hundred": "юз", "whole": "бутун", }, }

    @staticmethod
    def get_units(integer):
        lang_map = Numbers.lang_map[Numbers.lang]
        switcher = {1: lang_map["one"], 2: lang_map["two"], 3: lang_map["three"], 4: lang_map["four"],
                    5: lang_map["five"], 6: lang_map["six"], 7: lang_map["seven"], 8: lang_map["eight"],
                    9: lang_map["nine"], 0: ""}
        return switcher.get(integer, "")

    @staticmethod
    def get_tens(integer):
        lang_map = Numbers.lang_map[Numbers.lang]
        if integer < 10:
            return Numbers.get_units(integer)
        elif 10 <= integer < 20:
            if integer == 10:
                return lang_map["ten"]
            else:
                return lang_map["ten"] + " " + Numbers.get_units(integer % 10)
        elif 20 <= integer < 100:
            tens_switcher = {2: lang_map["twenty"], 3: lang_map["thirty"], 4: lang_map["forty"], 5: lang_map["fifty"],
                             6: lang_map["sixty"], 7: lang_map["seventy"], 8: lang_map["eighty"], 9: lang_map["ninety"]}
            tens = integer // 10
            units = integer % 10
            return tens_switcher.get(tens, "") + (" " + Numbers.get_units(units) if units != 0 else "")

    @staticmethod
    def convert_to_words(integer):
        if integer < 100:
            return Numbers.get_tens(integer)
        elif 100 <= integer < 1000:
            hundreds = integer // 100
            remainder = integer % 100
            return Numbers.get_units(hundreds) + " " + Numbers.lang_map[Numbers.lang]["hundred"] + (
                " " + Numbers.get_tens(remainder) if remainder != 0 else "")
        elif 1000 <= integer < 1000000:
            thousands = integer // 1000
            remainder = integer % 1000
            return Numbers.convert_to_words(thousands) + " " + Numbers.lang_map[Numbers.lang]["thousand"] + (
                " " + Numbers.convert_to_words(remainder) if remainder != 0 else "")
        elif 1000000 <= integer < 1000000000:
            millions = integer // 1000000
            remainder = integer % 1000000
            return Numbers.convert_to_words(millions) + " " + Numbers.lang_map[Numbers.lang]["million"] + (
                " " + Numbers.convert_to_words(remainder) if remainder != 0 else "")
        elif 1000000000 <= integer < 1000000000000:
            billions = integer // 1000000000
            remainder = integer % 1000000000
            return Numbers.convert_to_words(billions) + " " + Numbers.lang_map[Numbers.lang]["billion"] + (
                " " + Numbers.convert_to_words(remainder) if remainder != 0 else "")
        # Add trillions and beyond if needed.
        else:
            return "Number too large"


def get_full_voice(main_voice_path, output_path, debt=2234000, delay=3500):
    summa_list = Numbers.convert_to_words(debt).split(' ')
    numbers_audio = AudioSegment.from_file(f"number_voices/{summa_list[0]}.mp3")
    template_audio = AudioSegment.from_file(main_voice_path)
    # numbers_audio = speed_up_audio(numbers_audio, 1.2)

    for number in summa_list[1:]:
        silent_audio = AudioSegment.from_file(f"number_voices/{number}.mp3")
        chunks = split_on_silence(silent_audio, silence_thresh=-2000,
                                  keep_silence=False)  # Adjust silence_thresh as needed
        # Concatenate non-silent chunks
        non_silent_audio = AudioSegment.empty()
        for chunk in chunks:
            non_silent_audio += chunk
        # Concatenate with crossfade
        numbers_audio = numbers_audio.append(non_silent_audio, crossfade=500)
    combined_audio = template_audio[:delay] + numbers_audio + template_audio[delay:]
    # Export the result
    combined_audio.export(output_path, format="wav")


get_full_voice(r'C:\Users\Abdua\Downloads\analyze\scripts\default1.wav', 'audios/1.wav', delay=6200)
