import React from "react";
import { Skeleton, IconButton } from "@chakra-ui/react";
import {
  Table,
  Th,
  Td,
  Tr,
  Thead,
  Tbody,
  Editable,
  EditableInput,
  Image,
  EditablePreview,
} from "@chakra-ui/react";
import { DeleteIcon } from "@chakra-ui/icons";
import moment from "moment";
import CopyButton from "./CopyButton";
import { useSubscriptions } from "../core/hooks";
import ConfirmationRequest from "./ConfirmationRequest";

const List = (data) => {
  const { subscriptionsCache, changeNote, deleteSubscription } =
    useSubscriptions();

  const updateCallback = ({ id, note }) => {
    changeNote.mutate({ id, note });
  };

  if (subscriptionsCache.data) {
    return (
      <Table
        borderColor="gray.200"
        borderWidth="1px"
        variant="simple"
        colorScheme="primary"
        justifyContent="center"
        borderBottomRadius="xl"
        alignItems="baseline"
        h="auto"
        size="sm"
        mt={0}
      >
        <Thead>
          <Tr>
            <Th>Token</Th>
            <Th>Label</Th>
            <Th>Address</Th>
            <Th>Date Created</Th>
            <Th>Actions</Th>
          </Tr>
        </Thead>
        <Tbody>
          {subscriptionsCache.data.subscriptions.map((subscription) => {
            let iconLink;
            switch (subscription.subscription_type) {
              case "ethereum_blockchain":
                iconLink =
                  "https://ethereum.org/static/c48a5f760c34dfadcf05a208dab137cc/31987/eth-diamond-rainbow.png";
                break;
              case `ethereum_txpool`:
                iconLink =
                  "https://ethereum.org/static/a183661dd70e0e5c70689a0ec95ef0ba/31987/eth-diamond-purple.png";
                break;
              case `algorand_blockchain`:
                iconLink =
                  "https://www.algorand.com/assets/media-kit/logos/logo-marks/png/algorand_logo_mark_black.png";
                break;
              case `algorand_txpool`:
                iconLink =
                  "https://www.algorand.com/assets/media-kit/logos/logo-marks/png/algorand_logo_mark_white.png";
                break;
              default:
                console.error("no icon found for this pool");
            }
            return (
              <Tr key={`token-row-${subscription.address}`}>
                <Td>
                  <Image h="32px" src={iconLink} alt="pool icon" />
                </Td>
                <Td py={0}>
                  <Editable
                    colorScheme="primary"
                    placeholder="enter note here"
                    defaultValue={subscription.label}
                    onSubmit={(nextValue) =>
                      updateCallback({
                        id: subscription.id,
                        label: nextValue,
                      })
                    }
                  >
                    <EditablePreview
                      maxW="40rem"
                      _placeholder={{ color: "black" }}
                    />
                    <EditableInput maxW="40rem" />
                  </Editable>
                </Td>
                <Td mr={4} p={0}>
                  <CopyButton>{subscription.address}</CopyButton>
                </Td>
                <Td py={0}>{moment(subscription.created_at).format("L")}</Td>

                <Td py={0}>
                  <ConfirmationRequest
                    bodyMessage={"please confirm"}
                    header={"Delete subscription"}
                    onConfirm={() => deleteSubscription.mutate(subscription.id)}
                  >
                    <IconButton
                      size="sm"
                      variant="ghost"
                      colorScheme="primary"
                      icon={<DeleteIcon />}
                    />
                  </ConfirmationRequest>
                </Td>
              </Tr>
            );
          })}
        </Tbody>
      </Table>
    );
  } else if (subscriptionsCache.isLoading) {
    return <Skeleton />;
  } else {
    return "";
  }
};
export default List;
