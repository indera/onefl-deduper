"""
Goal: Store functions used for converting PHI data into hashed strings

@authors:
    Andrei Sura <sura.andrei@gmail.com>
"""

import os
import pandas as pd
from onefl.rules import AVAILABLE_RULES_MAP as rulz
from onefl import utils
from onefl.normalized_patient import NormalizedPatient  # noqa

pd.set_option('display.width', 1500)


# TODO: consider moving to a dedicated file
CONFIG = {
    'IN_DELIMITER': '\t',
    'EXPECTED_COLS': ['patid', 'first', 'last', 'dob', 'gender', 'race'],
    'OUT_DELIMITER': '\t',
    'OUT_FILE': 'phi_hashes.csv',
    'LINES_PER_CHUNK': 2000,
    'SALT': '',
    'ENABLED_RULES': ['F_L_D_G', 'F_L_D_R']
}


class ConfigErr(Exception):
    pass


class HashGenerator():
    log = None

    @classmethod
    def configure_logger(cls, logger):
        cls.log = logger

    @classmethod
    def _process_row_series(cls, ser, rule, pattern, required_attr, config):
        """
        :param config: dictionary with run-time parameters

        :rtype: string
        :return sha_string:
        """

        patient = NormalizedPatient(
            patid=ser['patid'],
            pat_first_name=ser['first'],
            pat_last_name=ser['last'],
            pat_birth_date=ser['dob'],
            pat_gender=ser['gender'],
            pat_race=ser['race']
        )
        # cls.log.info("Patient: {}".format(patient))

        if not patient.has_all_data(required_attr):
            cls.log.debug("Skip hashing patient [{}] due to missing data"
                          "for rule [{}]".format(patient.patid, rule))
            return ''

        raw = pattern.format(patient) + config['SALT']
        sha_string = utils.apply_sha256(raw)
        cls.log.debug("For patient [{}] (rule {}): {}, hash_string= {}".format(patient.patid, rule, raw, sha_string))  # noqa

        return sha_string

    @classmethod
    def _process_frame(cls, df_source, config):
        """
        Create a result frame

        Reminder:
            - apply() works on a row / column basis of a DataFrame
            - applymap() works element-wise on a DataFrame
            - map() works element-wise on a Series

        """
        df = pd.DataFrame()

        # keep the patid from the source
        df['patid'] = df_source['patid']

        for i, rule in enumerate(rulz):
            cls.log.debug("Applying rule {}: {}".format(i, rule))
            rule_data = rulz.get(rule)
            pattern = rule_data['pattern']
            required_attr = rule_data['required_attr']

            df[rule] = df_source.apply(
                lambda x: cls._process_row_series(x, rule, pattern,
                                                  required_attr,
                                                  config), axis=1)
        cls.log.debug("Processed frame: \n{}".format(df))
        return df

    @classmethod
    def validate_config(cls, config):
        """
        Helper method for preventing config errors
        """
        for rule_code in config.get('ENABLED_RULES'):
            if rule_code not in rulz:
                raise ConfigErr('Invalid rule code: [{}]! '
                                'Available codes are: {}'
                                .format(rule_code, rulz.keys()))

    @classmethod
    def generate(cls, inputdir, outputdir, config=CONFIG):
        """
        Read the "phi_data.csv" file and generate "hashes.csv"
        containing two (or more) sha256 strings for each line
        in the input file.

        This method is invoked from

        .. seealso::

            ../gen_hashes.py

        :param inputdir: directory name for the source file
        :param outputdir: directory name for generated file

        :rtype: DataFrame
        :return the frame with hashes of the PHI data

        Columns:
            - patid
            - sha_rule_1 (first_last_dob_gender)
            - sha_rule_2 (first_last_dob_race)

        """
        cls.validate_config(config)
        EXPECTED_COLS = config['EXPECTED_COLS']
        cls.log.info("Using [{}] as source folder".format(inputdir))
        cls.log.info("Using [{}] as salt".format(config['SALT']))
        cls.log.info("Expecting input file to contain columns: {}"
                     .format(EXPECTED_COLS))
        cls.log.info("Using [{}] as destination folder".format(outputdir))

        # TODO: add step for validating input column names
        # TODO: add config to allow adding more rules

        in_file = os.path.join(inputdir, 'phi.csv')
        reader = None

        try:
            reader = pd.read_csv(in_file,
                                 sep=config['IN_DELIMITER'],
                                 dtype=object,
                                 skipinitialspace=True,
                                 skip_blank_lines=True,
                                 usecols=list(EXPECTED_COLS),
                                 chunksize=config['LINES_PER_CHUNK'],
                                 iterator=True)
            cls.log.info("Reading data from file: {} ({})"
                         .format(in_file, utils.get_file_size(in_file)))

        except ValueError as exc:
            cls.log.info("Please check if the actual column names"
                         " in [{}] match the expected column names"
                         " file: {}.".format(in_file,
                                             sorted(EXPECTED_COLS)))
            cls.log.error("Error: {}".format(exc))

        frames = []

        for df_source in reader:
            df_source.fillna('', inplace=True)
            df = cls._process_frame(df_source, config)
            frames.append(df)

        df = pd.concat(frames, ignore_index=True)

        # Concatenation can re-order columns so we need to enforce the order
        out_columns = ['patid']
        out_columns.extend(config['ENABLED_RULES'])

        out_file = os.path.join(outputdir, config['OUT_FILE'])
        utils.frame_to_file(df[out_columns], out_file,
                            delimiter=config['OUT_DELIMITER'])

        cls.log.info("Wrote output file: {} ({} data rows, {})"
                     .format(out_file,
                             len(df),
                             utils.get_file_size(out_file)))
        return True