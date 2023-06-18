from hashlib import sha256
from petlib.bn import Bn

import helper
from helper import BpGroupHelper
from pubKey import PubKey
from request import Request


class Client:
    def __init__(self, idp_pk):
        """
        Constructor for the client

        :param idp_pk: The public key of the IdP
        """
        self.__idp_pk: PubKey = idp_pk
        self.__t = None

    def request_id(self, attributes, data):
        """
        Implementation of the 'Multi-Message Protocol' of the paper
        Short Randomizable Signatures the user side
        https://doi.org/10.1007/978-3-319-29485-8_7
        We only need to hide and then prove knowledge of the hidden attributes

        :param attributes: users attribute.
        The format of the attributes is ["attribute", "True if hidden false otherwise]
        :param data: data used for the NIZK verification (like time stamp etc.)
        :return: A request object to be sent to the IdP
        """
        # We need the attributes hashed for processing (only the hidden attributes)
        hashed_attributes = self.__hash_hidden_attributes(attributes)
        C = self.__create_commitment(hashed_attributes, attributes)
        V, c, r = self.create_zkp(attributes, hashed_attributes, C, data)
        # We will send to the IdP the rest of the attributes in plaintext, but we add "" for placeholder of the hidden
        request_attributes = ["" if attr[1] else attr[0] for attr in attributes]
        return Request(C, c, r, request_attributes)

    def __hash_hidden_attributes(self, attributes):
        """
        hash all the hidden attributes using SHA256

        :param attributes: The attributes to be hashed
        :return: The hashed hidden attributes
        """
        hashed_attributes = []
        for attribute in attributes:
            # Check if it is a hidden attribute
            if attribute[1]:
                hashed_attributes.append(Bn.from_binary(sha256(attribute[0]).digest()))
        return hashed_attributes

    def __create_commitment(self, hashed_attributes, attributes):
        """
        Create the commitment in the hidden values
        C = g1^random * Yg1i ^hash(attribute_i)

        :param hashed_attributes: The hashed hidden attributes
        :param attributes: All the attributes (hidden + plain)
        :return: a commitment C to the hidden attributes
        """
        o: Bn = BpGroupHelper.o
        # t is going to be the blinding factor, and we need to unblind later
        t = o.random()
        self.__t = t
        C = self.__idp_pk.g1 * t
        j = 0
        for i, attribute in enumerate(attributes):
            if attribute[1]:
                # Calculate C
                C += self.__idp_pk.Yg1[i] * hashed_attributes[j]
                j += 1
        return C

    def create_zkp(self, attributes, hashed_attributes, C, data):
        """
        V = g1 ^ random1 * Yg1i ^ random2i
        c = Hash(C || V || data)
        r1 = random1 - t * c
        r2i = random2i - attribute_i * c

        :return:
        """
        o: Bn = BpGroupHelper.o
        randomness = [o.random()]
        # Calculate V
        V = self.__idp_pk.g1 * randomness[0]
        for i, attribute in enumerate(attributes):
            if attribute[1]:
                randomness.append(o.random())
                V += self.__idp_pk.Yg1[i] * randomness[i + 1]
        # Calculate c
        c = helper.to_challenge([C.export(), V.export(), data])
        # Calculate r's
        r = [randomness[0] - self.__t * c]
        for i, attribute in enumerate(hashed_attributes):
            r.append(randomness[i+1] - attribute * c)
        return V, c, r

    def unbind_sig(self, sig_prime):
        """
        Unblind the signature generated by the IdP
        sig = sig_prime1, sig_prime2 / sig_prime1 ^ randomness_used_in_sign

        :param sig_prime: The blinded signature
        :return: The un-blinded signature
        """
        sig1, sig2 = sig_prime
        return sig1, sig2 - sig1 * self.__t

    def verify(self, sig, attributes):
        """
        Verify that the blinded signature provided by the IdP is correctly formed
        check if e(sig1, X_prime * Yg2i^hash(attribute_i)) = e(sig2, g2)

        :param sig: the un-blinded signature
        :param attributes: the attributes that the signature was signed over
        :return: true if it is correct false otherwise
        """
        sig1, sig2 = sig
        verification_result = self.__idp_pk.X
        for i, attribute in enumerate(attributes):
            attribute_hash = Bn.from_binary(sha256(attribute[0]).digest())
            verification_result += self.__idp_pk.Yg2[i] * attribute_hash
        return BpGroupHelper.e(sig1, verification_result) == BpGroupHelper.e(sig2, self.__idp_pk.g2)
